"""AV Access HDMI Matrix integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AVAccessApiClient
from .coordinator import AVAccessCoordinator


PLATFORMS: list[Platform] = [
    Platform.SELECT,
]


type AVAccessConfigEntry = ConfigEntry[AVAccessCoordinator]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
) -> bool:
    """Set up AV Access HDMI Matrix from a config entry."""

    session = async_get_clientsession(hass)

    client = AVAccessApiClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        session=session,
    )

    coordinator = AVAccessCoordinator(
        hass=hass,
        client=client,
        config_entry=entry,
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
