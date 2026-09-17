"""AV Access HDMI Matrix integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import AVAccessClient, AVAccessError
from .coordinator import AVAccessCoordinator

PLATFORMS: list[Platform] = [
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
