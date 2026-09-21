"""Number platform for the AV Access HDMI matrix integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .const import CEC_DELAY_MAX, CEC_DELAY_MIN, TRANSLATION_KEY_OUTPUT_CEC_DELAY
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
    """Set up AV Access HDMI matrix number entities."""
    coordinator = entry.runtime_data

    # A matrix that does not support CEC reports no CEC state at all.
    async_add_entities(
        AVAccessCecDelayNumber(
            coordinator=coordinator,
            output=output,
        )
        for output in sorted(coordinator.data["cec_delay"])
    )


class AVAccessCecDelayNumber(AVAccessEntity, NumberEntity):
    """Set the automatic CEC power off delay of a matrix output.

    The matrix powers the sink of the output off over CEC once the output has
    been without an active signal for this many minutes.
    """

    _attr_translation_key = TRANSLATION_KEY_OUTPUT_CEC_DELAY
    _reports_external_change = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = float(CEC_DELAY_MIN)
    _attr_native_max_value = float(CEC_DELAY_MAX)
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the CEC power off delay number."""
        super().__init__(coordinator)

        self._output = output

        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_cec_delay"
        )

        self._name_after_output(output)

    @property
    def native_value(self) -> float | None:
        """Return the configured delay in minutes."""
        return self.coordinator.data["cec_delay"].get(self._output)

    async def async_set_native_value(self, value: float) -> None:
        """Set the delay in minutes."""
        await self.coordinator.async_set_cec_delay(self._output, int(value))
