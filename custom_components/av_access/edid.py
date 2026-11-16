"""Read the list of EDIDs a matrix offers from its web interface.

The command set of the matrix has no command that lists its EDIDs. The web
interface is a single page that carries the list in its script, and the matrix
hands that page out without a login. The list differs between firmware
versions, which is why it is read from the device instead of being part of the
integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
import logging
import re
from typing import Any

import aiohttp
from yarl import URL

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_EDID_LABELS,
    CONF_EDID_OPTIONS,
    CONF_EDID_OPTIONS_SOURCE,
    DEFAULT_EDID_OPTIONS,
    EDID_LIST_RETRY_INTERVAL,
    EDID_LIST_TIMEOUT,
    EDID_SOURCE_DEVICE,
    EDID_SOURCE_FALLBACK,
)
from .issues import (
    async_create_edid_labels_changed_issue,
    async_create_edid_list_fallback_issue,
    async_delete_edid_list_fallback_issue,
)
from .labels import device_edid_options, remap_edid_labels, stored_labels

_LOGGER = logging.getLogger(__name__)

# The page defines the list as hdmiList:[{desc:"Smart EDID",val:"14"},...].
EDID_LIST_PATTERN = re.compile(r"hdmiList\s*:\s*\[(.*?)\]", re.DOTALL)
EDID_ENTRY_PATTERN = re.compile(
    r'\{\s*desc\s*:\s*"([^"]*)"\s*,\s*val\s*:\s*"(\d+)"\s*\}'
)

# This entry of the list is no EDID. The web interface opens a dialog to upload
# an EDID file when it is selected.
EDID_WRITE_DESCRIPTION = "edid write"


class EdidListNotFoundError(Exception):
    """Raised when the web interface of the matrix does not provide the list."""


def parse_edid_options(html: str) -> dict[str, str]:
    """Return the EDIDs listed in the page of the web interface.

    The result maps the value the matrix expects to the description it shows.
    """
    if (block := EDID_LIST_PATTERN.search(html)) is None:
        raise EdidListNotFoundError("The page of the matrix contains no EDID list")

    options = {
        value: description.strip()
        for description, value in EDID_ENTRY_PATTERN.findall(block.group(1))
        if description.strip()
        and description.strip().casefold() != EDID_WRITE_DESCRIPTION
    }

    if not options:
        raise EdidListNotFoundError("The EDID list of the matrix is empty")

    return options


async def async_fetch_edid_options(
    session: aiohttp.ClientSession,
    host: str,
) -> dict[str, str]:
    """Return the EDID list from the web interface of the matrix."""
    try:
        async with session.get(
            URL.build(scheme="http", host=host),
            timeout=aiohttp.ClientTimeout(total=EDID_LIST_TIMEOUT),
        ) as response:
            response.raise_for_status()

            # The matrix does not name a charset, and a page that is not valid
            # UTF-8 in some unrelated place still contains the list.
            html = await response.text(encoding="utf-8", errors="replace")

    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise EdidListNotFoundError(
            f"The web interface of the matrix could not be read: {err!r}"
        ) from err

    return parse_edid_options(html)


async def async_read_edid_options(
    hass: HomeAssistant,
    host: str,
) -> tuple[dict[str, str], str]:
    """Return the EDID list of the matrix and where it came from.

    A matrix whose web interface cannot be read is still usable, so the list of
    the firmware the integration was developed against stands in for it.
    """
    try:
        options = await async_fetch_edid_options(async_get_clientsession(hass), host)

    except EdidListNotFoundError as err:
        _LOGGER.warning(
            "Unable to read the EDID list of the AV Access matrix at %s, using "
            "the built-in list until it can be read: %s",
            host,
            err,
        )

        return dict(DEFAULT_EDID_OPTIONS), EDID_SOURCE_FALLBACK

    return options, EDID_SOURCE_DEVICE


@callback
def async_remap_edid_labels(
    hass: HomeAssistant,
    entry: ConfigEntry,
    data: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Return the options of an entry that is about to get new data.

    The names of the EDIDs move along with their descriptions if the EDID list
    in the new data differs, and the user is asked to check every name that
    could not. Also returns whether the list differs, which changes the options
    of the EDID selects.
    """
    previous = device_edid_options(entry.data)
    current = device_edid_options(data)
    options = dict(entry.options)

    if current == previous:
        return options, False

    labels, changed = remap_edid_labels(
        stored_labels(entry.options, CONF_EDID_LABELS),
        previous,
        current,
    )
    options[CONF_EDID_LABELS] = labels

    if changed:
        async_create_edid_labels_changed_issue(hass, entry, changed)

    return options, True


@callback
def async_start_edid_list_refresh(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Read the EDID list of the matrix until it succeeds.

    The built-in list only stands in while the web interface of the matrix
    cannot be read, for example because the matrix was switched off while Home
    Assistant started. A repair issue tells the user meanwhile, so the warning
    in the log is only written once.
    """
    unsubscribe: CALLBACK_TYPE | None = None
    warned = False

    @callback
    def _async_stop() -> None:
        nonlocal unsubscribe

        if unsubscribe is not None:
            unsubscribe()
            unsubscribe = None

    async def _async_refresh(_now: datetime | None = None) -> None:
        nonlocal warned

        host = entry.data[CONF_HOST]

        try:
            options = await async_fetch_edid_options(
                async_get_clientsession(hass), host
            )

        except EdidListNotFoundError as err:
            _LOGGER.log(
                logging.DEBUG if warned else logging.WARNING,
                "Unable to read the EDID list of the AV Access matrix at %s, "
                "using the built-in list until it can be read: %s",
                host,
                err,
            )
            warned = True

            async_create_edid_list_fallback_issue(hass, entry)
            return

        _async_stop()

        data = {
            **entry.data,
            CONF_EDID_OPTIONS: options,
            CONF_EDID_OPTIONS_SOURCE: EDID_SOURCE_DEVICE,
        }
        entry_options, list_changed = async_remap_edid_labels(hass, entry, data)

        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=entry_options,
        )
        async_delete_edid_list_fallback_issue(hass, entry)

        # The options of the EDID selects are fixed when they are created.
        if list_changed:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    unsubscribe = async_track_time_interval(
        hass,
        _async_refresh,
        timedelta(seconds=EDID_LIST_RETRY_INTERVAL),
        name="AV Access EDID list",
        cancel_on_shutdown=True,
    )
    entry.async_on_unload(_async_stop)
    entry.async_create_background_task(
        hass,
        _async_refresh(),
        "av_access_edid_list",
    )
