"""AV Access HDMI-Matrix integration for Home Assistant."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.SELECT,
    Platform.BUTTON,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up AV Access HDMI-Matrix from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload an AV Access HDMI-Matrix config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)