"""Read the list of EDIDs a matrix offers from its web interface.

The command set of the matrix has no command that lists its EDIDs. The web
interface is a single page that carries the list in its script, and the matrix
hands that page out without a login. The list differs between firmware
versions, which is why it is read from the device instead of being part of the
integration.
"""

from __future__ import annotations

import logging
import re

import aiohttp
from yarl import URL

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DEFAULT_EDID_OPTIONS,
    EDID_LIST_TIMEOUT,
    EDID_SOURCE_DEVICE,
    EDID_SOURCE_FALLBACK,
)

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
            "the built-in list instead. Reconfigure the integration to read it "
            "again: %s",
            host,
            err,
        )

        return dict(DEFAULT_EDID_OPTIONS), EDID_SOURCE_FALLBACK

    return options, EDID_SOURCE_DEVICE
