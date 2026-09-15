"""Base entity for the AV Access HDMI-Matrix integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AVAccessCoordinator


class AVAccessEntity(CoordinatorEntity[AVAccessCoordinator]):
    """Base entity for AV Access HDMI-Matrix entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AVAccessCoordinator) -> None:
        """Initialize the AV Access HDMI-Matrix entity."""
        super().__init__(coordinator)

        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, coordinator.config_entry.entry_id),
            },
            name=coordinator.config_entry.title,
            manufacturer="AV Access",
        )