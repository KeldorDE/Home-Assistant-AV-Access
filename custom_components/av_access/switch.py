"""Switch platform for the AV Access HDMI matrix integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .const import TRANSLATION_KEY_INPUT_HDCP
from .coordinator import AVAccessCoordinator
from .entity import AVAccessEntity

# The coordinator handles all data updates, so the entities do not need to be
# updated in parallel.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AV Access HDMI matrix switch entities."""
    coordinator = entry.runtime_data

    # A matrix that does not support HDCP reports no HDCP state at all.
    async_add_entities(
        AVAccessHdcpSwitch(
            coordinator=coordinator,
            input_number=input_number,
        )
        for input_number in sorted(coordinator.data["hdcp"])
    )


class AVAccessHdcpSwitch(AVAccessEntity, SwitchEntity):
    """Enable or disable HDCP support for a matrix input."""

    _attr_translation_key = TRANSLATION_KEY_INPUT_HDCP
    _reports_external_change = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        input_number: int,
    ) -> None:
        """Initialize the HDCP switch."""
        super().__init__(coordinator)

        self._input = input_number

        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_input_{input_number}_hdcp"
        )

        self._name_after_input(input_number)

    @property
    def is_on(self) -> bool | None:
        """Return whether HDCP support is enabled."""
        return self.coordinator.data["hdcp"].get(self._input)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable HDCP support."""
        await self._async_set_hdcp(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable HDCP support."""
        await self._async_set_hdcp(False)

    async def _async_set_hdcp(self, enabled: bool) -> None:
        """Apply the requested HDCP state."""
        await self.coordinator.async_set_hdcp(
            self._input,
            enabled,
        )
