"""AV Access HDMI Matrix integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import AVAccessClient, AVAccessError
from .const import CONF_EDID_OPTIONS_SOURCE, EDID_SOURCE_DEVICE
from .coordinator import AVAccessCoordinator
from .edid import async_start_edid_list_refresh
from .issues import async_delete_edid_list_fallback_issue, async_delete_issues

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


type AVAccessConfigEntry = ConfigEntry[AVAccessCoordinator]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
) -> bool:
    """Set up AV Access HDMI Matrix from a config entry."""
    client = AVAccessClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
    )

    # The static device information determines the device details and the number
    # of entities, so it is read before the platforms are set up.
    try:
        device_info = await client.async_get_device_info()

    except AVAccessError as err:
        raise ConfigEntryNotReady(
            f"Unable to read the AV Access matrix device information: {err}"
        ) from err

    coordinator = AVAccessCoordinator(
        hass=hass,
        client=client,
        config_entry=entry,
        device_info=device_info,
    )

    # Perform the first update before loading entities.
    await coordinator.async_config_entry_first_refresh()

    # Make the coordinator available to all platforms.
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    # An entry that was set up before the EDID list was read from the matrix,
    # or while its web interface could not be read, uses the built-in list. The
    # list of the matrix is read in the background instead of delaying the
    # start, and the entry reloads once it differs. This only starts once the
    # matrix answered, so a setup that is retried does not start it each time.
    if entry.data.get(CONF_EDID_OPTIONS_SOURCE) == EDID_SOURCE_DEVICE:
        async_delete_edid_list_fallback_issue(hass, entry)
    else:
        async_start_edid_list_refresh(hass, entry)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
) -> bool:
    """Unload an AV Access HDMI Matrix config entry."""
    return await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )


async def async_remove_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
) -> None:
    """Withdraw the repair issues of an AV Access HDMI Matrix that is removed."""
    async_delete_issues(hass, entry)
