"""Select platform for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .const import (
    EDID_OPTION_BY_VALUE,
    EDID_VALUE_BY_OPTION,
    INPUT_OPTION_BY_VALUE,
    INPUT_VALUE_BY_OPTION,
    TRANSLATION_KEY_INPUT_EDID,
    TRANSLATION_KEY_OUTPUT_INPUT,
)
from .coordinator import AVAccessCoordinator
from .entity import AVAccessEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AV Access HDMI-Matrix select entities."""
    coordinator = entry.runtime_data

    entities = []

    for output in range(1, 5):
        entities.append(
            AVAccessOutputSelect(
                coordinator=coordinator,
                output=output,
            )
        )

    for input_number in range(1, 5):
        entities.append(
            AVAccessEdidSelect(
                coordinator=coordinator,
                input_number=input_number,
            )
        )

    async_add_entities(entities)


class AVAccessOutputSelect(AVAccessEntity, SelectEntity):
    """Select the HDMI input for a matrix output."""

    _attr_translation_key = TRANSLATION_KEY_OUTPUT_INPUT
    _attr_options = list(INPUT_OPTION_BY_VALUE.values())

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the output select."""
        super().__init__(coordinator)

        self._output = output

        self._attr_translation_placeholders = {"output": str(output)}
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_input"
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected input."""
        value = self.coordinator.data.get("outputs", {}).get(str(self._output))

        if value is None:
            return None

        try:
            return INPUT_OPTION_BY_VALUE.get(int(value))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        """Select an HDMI input."""
        input_number = INPUT_VALUE_BY_OPTION.get(option)

        if input_number is None:
            raise ServiceValidationError(f"Unsupported input option: {option}")

        await self.coordinator.client.set_output(
            self._output,
            input_number,
        )

        await self.coordinator.async_request_refresh()


class AVAccessEdidSelect(AVAccessEntity, SelectEntity):
    """Select the EDID for a matrix input."""

    _attr_translation_key = TRANSLATION_KEY_INPUT_EDID
    _attr_options = list(EDID_OPTION_BY_VALUE.values())

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        input_number: int,
    ) -> None:
        """Initialize the EDID select."""
        super().__init__(coordinator)

        self._input = input_number

        self._attr_translation_placeholders = {"input": str(input_number)}
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_input_{input_number}_edid"
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected EDID."""
        value = self.coordinator.data.get("edid", {}).get(str(self._input))

        if value is None:
            return None

        try:
            return EDID_OPTION_BY_VALUE.get(int(value))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        """Select an EDID."""
        edid = EDID_VALUE_BY_OPTION.get(option)

        if edid is None:
            raise ServiceValidationError(f"Unsupported EDID option: {option}")

        await self.coordinator.client.set_edid(
            self._input,
            edid,
        )

        await self.coordinator.async_request_refresh()
