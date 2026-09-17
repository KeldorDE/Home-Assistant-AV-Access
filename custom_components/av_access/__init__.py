"""AV Access HDMI Matrix integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AVAccessApiClient, AVAccessApiError
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

    # The static device information determines the device details and the number
    # of entities, so it is read before the platforms are set up.
    try:
        device_info = await client.get_device_info()

    except AVAccessApiError as err:
        raise ConfigEntryNotReady(
            f"Unable to read the AV Access HDMI-Matrix device information: {err}"
        ) from err

    # Earlier versions derived the unique ID from the connection details.
    if entry.unique_id != device_info.unique_id:
        hass.config_entries.async_update_entry(
            entry,
            unique_id=device_info.unique_id,
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
