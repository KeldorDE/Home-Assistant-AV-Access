"""Select platform for the AV Access HDMI-Matrix integration."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .coordinator import AVAccessCoordinator
from .entity import AVAccessEntity

INPUT_OPTIONS = [
    "HDMI 1",
    "HDMI 2",
    "HDMI 3",
    "HDMI 4",
]

EDID_OPTIONS = [
    "Copy from Output 1",
    "Copy from Output 2",
    "Copy from Output 3",
    "Copy from Output 4",
]


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

    _attr_options = INPUT_OPTIONS

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the output select."""
        super().__init__(coordinator)

        self._output = output

        self._attr_name = f"Output {output} Input"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_input"
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected input."""
        value = self.coordinator.data.get("outputs", {}).get(str(self._output))

        if value is None:
            return None

        return f"HDMI {value}"

    async def async_select_option(self, option: str) -> None:
        """Select an HDMI input."""
        input_number = int(option.removeprefix("HDMI "))

        await self.coordinator.client.set_output(
            self._output,
            input_number,
        )

        await self.coordinator.async_request_refresh()


class AVAccessEdidSelect(AVAccessEntity, SelectEntity):
    """Select the EDID for a matrix input."""

    _attr_options = EDID_OPTIONS

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        input_number: int,
    ) -> None:
        """Initialize the EDID select."""
        super().__init__(coordinator)

        self._input = input_number

        self._attr_name = f"Input {input_number} EDID"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_input_{input_number}_edid"
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected EDID."""
        return self.coordinator.data.get("edid", {}).get(str(self._input))

    async def async_select_option(self, option: str) -> None:
        """Select an EDID."""
        await self.coordinator.client.set_edid(
            self._input,
            option,
        )

        await self.coordinator.async_request_refresh()
