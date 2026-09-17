"""Sensor platform exposing the configured port names.

The names are meant to be used in dashboards, for example as a heading above
the select of an output.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .const import (
    TRANSLATION_KEY_INPUT_NAME,
    TRANSLATION_KEY_OUTPUT_INPUT_NUMBER,
    TRANSLATION_KEY_OUTPUT_NAME,
)
from .coordinator import AVAccessCoordinator
from .entity import AVAccessEntity
from .labels import input_name, output_name

# The names only change when the options change, which reloads the entry.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AV Access HDMI matrix name sensors."""
    coordinator = entry.runtime_data
    device = coordinator.device_info

    entities: list[SensorEntity] = [
        AVAccessInputNameSensor(
            coordinator=coordinator,
            input_number=input_number,
        )
        for input_number in range(1, device.input_count + 1)
    ]

    entities.extend(
        AVAccessOutputNameSensor(
            coordinator=coordinator,
            output=output,
        )
        for output in range(1, device.output_count + 1)
    )

    entities.extend(
        AVAccessOutputInputNumberSensor(
            coordinator=coordinator,
            output=output,
        )
        for output in range(1, device.output_count + 1)
    )

    async_add_entities(entities)


class AVAccessInputNameSensor(AVAccessEntity, SensorEntity):
    """Expose the name of a matrix input."""

    _attr_translation_key = TRANSLATION_KEY_INPUT_NAME

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        input_number: int,
    ) -> None:
        """Initialize the input name sensor."""
        super().__init__(coordinator)

        self._attr_native_value = input_name(
            coordinator.config_entry.options,
            input_number,
        )
        self._attr_translation_placeholders = {"input": str(input_number)}
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_input_{input_number}_name"
        )


class AVAccessOutputNameSensor(AVAccessEntity, SensorEntity):
    """Expose the name of a matrix output."""

    _attr_translation_key = TRANSLATION_KEY_OUTPUT_NAME

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the output name sensor."""
        super().__init__(coordinator)

        self._attr_native_value = output_name(
            coordinator.config_entry.options,
            output,
        )
        self._attr_translation_placeholders = {"output": str(output)}
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_name"
        )


class AVAccessOutputInputNumberSensor(AVAccessEntity, SensorEntity):
    """Expose the number of the input currently routed to an output.

    The select of an output reports the name of the input, so this sensor
    provides the raw number that an automation or a template can work with.
    """

    _attr_translation_key = TRANSLATION_KEY_OUTPUT_INPUT_NUMBER
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the input number sensor."""
        super().__init__(coordinator)

        self._output = output

        self._attr_translation_placeholders = {"output": str(output)}
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_input_number"
        )

    @property
    def native_value(self) -> int | None:
        """Return the number of the routed input."""
        return self.coordinator.data["outputs"].get(str(self._output))
