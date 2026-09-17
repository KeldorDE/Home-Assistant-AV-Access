"""Select platform for the AV Access HDMI matrix integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .const import (
    EDID_OPTION_BY_VALUE,
    EDID_VALUE_BY_OPTION,
    TRANSLATION_KEY_INPUT_EDID,
    TRANSLATION_KEY_OUTPUT_INPUT,
)
from .coordinator import AVAccessCoordinator
from .entity import AVAccessEntity
from .labels import input_options, values_by_option

# The coordinator handles all data updates, so the entities do not need to be
# updated in parallel.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AV Access HDMI matrix select entities."""
    coordinator = entry.runtime_data
    device = coordinator.device_info

    entities: list[SelectEntity] = [
        AVAccessOutputSelect(
            coordinator=coordinator,
            output=output,
        )
        for output in range(1, device.output_count + 1)
    ]

    entities.extend(
        AVAccessEdidSelect(
            coordinator=coordinator,
            input_number=input_number,
        )
        for input_number in range(1, device.input_count + 1)
    )

    async_add_entities(entities)


class AVAccessOutputSelect(AVAccessEntity, SelectEntity):
    """Select the HDMI input for a matrix output."""

    _attr_translation_key = TRANSLATION_KEY_OUTPUT_INPUT
    _reports_external_change = True

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the output select."""
        super().__init__(coordinator)

        self._output = output

        options = input_options(
            coordinator.config_entry.options,
            coordinator.device_info.input_count,
        )

        self._option_by_value = options
        self._value_by_option = values_by_option(options)

        self._attr_options = list(options.values())
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_input"
        )

        self._name_after_output(output)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected input."""
        value = self.coordinator.data["outputs"].get(str(self._output))

        if value is None:
            return None

        return self._option_by_value.get(value)

    async def async_select_option(self, option: str) -> None:
        """Select an HDMI input."""
        input_number = self._value_by_option.get(option)

        if input_number is None:
            raise ServiceValidationError(f"Unsupported input option: {option}")

        await self.coordinator.async_set_output(
            self._output,
            input_number,
        )


class AVAccessEdidSelect(AVAccessEntity, SelectEntity):
    """Select the EDID for a matrix input."""

    _attr_translation_key = TRANSLATION_KEY_INPUT_EDID
    _reports_external_change = True
    # The EDID options are named by the matrix itself and are not renameable.
    _attr_options = list(EDID_OPTION_BY_VALUE.values())

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        input_number: int,
    ) -> None:
        """Initialize the EDID select."""
        super().__init__(coordinator)

        self._input = input_number

        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_input_{input_number}_edid"
        )

        self._name_after_input(input_number)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected EDID."""
        value = self.coordinator.data["edid"].get(str(self._input))

        if value is None:
            return None

        return EDID_OPTION_BY_VALUE.get(value)

    async def async_select_option(self, option: str) -> None:
        """Select an EDID."""
        edid = EDID_VALUE_BY_OPTION.get(option)

        if edid is None:
            raise ServiceValidationError(f"Unsupported EDID option: {option}")

        await self.coordinator.async_set_edid(
            self._input,
            edid,
        )
