"""AV Access HDMI Matrix integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import AVAccessClient, AVAccessError
from .const import CONF_EDID_OPTIONS, CONF_EDID_OPTIONS_SOURCE
from .coordinator import AVAccessCoordinator
from .edid import async_read_edid_options

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

    # An entry that was set up before the EDID list was read from the matrix
    # has none. It is read once here, the configuration dialog refreshes it.
    if CONF_EDID_OPTIONS not in entry.data:
        edid_options, edid_source = await async_read_edid_options(
            hass,
            entry.data[CONF_HOST],
        )

        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_EDID_OPTIONS: edid_options,
                CONF_EDID_OPTIONS_SOURCE: edid_source,
            },
        )

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
