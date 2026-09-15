"""Button platform for the AV Access HDMI-Matrix integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AVAccessConfigEntry
from .coordinator import AVAccessCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AV Access HDMI-Matrix buttons."""
    coordinator = entry.runtime_data

    async_add_entities(
        [
            AVAccessRefreshButton(coordinator),
        ]
    )


class AVAccessRefreshButton(
    CoordinatorEntity[AVAccessCoordinator],
    ButtonEntity,
):
    """Button to refresh the AV Access HDMI-Matrix state."""

    _attr_has_entity_name = True
    _attr_name = "Refresh"

    def __init__(self, coordinator: AVAccessCoordinator) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_refresh"

    async def async_press(self) -> None:
        """Refresh the matrix state."""
        await self.coordinator.async_request_refresh()