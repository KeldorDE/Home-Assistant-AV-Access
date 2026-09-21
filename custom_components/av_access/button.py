"""Button platform for the AV Access HDMI matrix integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .const import (
    TRANSLATION_KEY_OUTPUT_CEC_POWER_OFF,
    TRANSLATION_KEY_OUTPUT_CEC_POWER_ON,
)
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
    """Set up AV Access HDMI matrix button entities."""
    coordinator = entry.runtime_data

    entities: list[ButtonEntity] = []

    # A matrix that does not support CEC reports no CEC state at all, so the
    # outputs of the automatic CEC power function are the ones that accept the
    # manual CEC power commands as well.
    for output in sorted(coordinator.data["cec_auto"]):
        entities.append(
            AVAccessCecPowerButton(
                coordinator=coordinator,
                output=output,
                power_on=True,
            )
        )
        entities.append(
            AVAccessCecPowerButton(
                coordinator=coordinator,
                output=output,
                power_on=False,
            )
        )

    async_add_entities(entities)


class AVAccessCecPowerButton(AVAccessEntity, ButtonEntity):
    """Power the sink of a matrix output on or off over CEC.

    The matrix only passes the command on to the sink and never reports its
    power state, so this is a button instead of a switch.
    """

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
        power_on: bool,
    ) -> None:
        """Initialize the CEC power button."""
        self._attr_translation_key = (
            TRANSLATION_KEY_OUTPUT_CEC_POWER_ON
            if power_on
            else TRANSLATION_KEY_OUTPUT_CEC_POWER_OFF
        )

        super().__init__(coordinator)

        self._output = output
        self._power_on = power_on

        # A CEC power command matches none of the button device classes, so the
        # direction of the command is only shown by the icon.
        self._attr_icon = "mdi:television" if power_on else "mdi:television-off"

        suffix = "on" if power_on else "off"

        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_cec_power_{suffix}"
        )

        self._name_after_output(output)

    async def async_press(self) -> None:
        """Send the CEC power command to the sink."""
        await self.coordinator.async_set_cec_power(self._output, self._power_on)
