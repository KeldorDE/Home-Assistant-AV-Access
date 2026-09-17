"""Base entity for the AV Access HDMI matrix integration."""

from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Context, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EVENT_EXTERNAL_CHANGE,
    MANUFACTURER,
    PLACEHOLDER_INPUT,
    PLACEHOLDER_NAME,
    PLACEHOLDER_OUTPUT,
    TRANSLATION_KEY_NAMED_SUFFIX,
)
from .coordinator import AVAccessCoordinator
from .labels import input_custom_name, output_custom_name

_UNKNOWN = object()


class AVAccessEntity(CoordinatorEntity[AVAccessCoordinator]):
    """Base entity for AV Access HDMI matrix entities."""

    _attr_has_entity_name = True

    # Entities whose state the matrix can also change at the front panel or with
    # the remote control report such a change to the logbook.
    _reports_external_change = False

    def __init__(self, coordinator: AVAccessCoordinator) -> None:
        """Initialize the AV Access HDMI matrix entity."""
        super().__init__(coordinator)

        # The state of the last update, used to notice a change the matrix made
        # on its own.
        self._previous_state: Any = _UNKNOWN

        device = coordinator.device_info

        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, coordinator.config_entry.entry_id),
            },
            name=coordinator.config_entry.title,
            manufacturer=device.manufacturer or MANUFACTURER,
            model=device.model,
            sw_version=device.sw_version,
            hw_version=device.hw_version,
            configuration_url=device.configuration_url,
        )

    async def async_added_to_hass(self) -> None:
        """Remember the current state before the first update arrives."""
        await super().async_added_to_hass()

        if self._reports_external_change:
            self._previous_state = self.state

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write the new state, telling the logbook where a change came from."""
        if self._reports_external_change:
            self._async_report_external_change()

        super()._handle_coordinator_update()

    @callback
    def _async_report_external_change(self) -> None:
        """Fire an event for a state the matrix changed without a command.

        A state change only names its origin in the logbook if it shares the
        context with an event describing it. Home Assistant sets that context
        for its own commands, so only a change made at the front panel or with
        the remote control needs one.
        """
        state = self.state
        previous_state = self._previous_state

        self._previous_state = state

        if (
            self.coordinator.command_update
            or previous_state is _UNKNOWN
            or state == previous_state
        ):
            return

        context = Context()

        self.async_set_context(context)

        self.hass.bus.async_fire(
            EVENT_EXTERNAL_CHANGE,
            {ATTR_ENTITY_ID: self.entity_id},
            context=context,
        )

    def _name_after_input(self, number: int) -> None:
        """Name the entity after the input it belongs to."""
        self._name_after_port(
            placeholder=PLACEHOLDER_INPUT,
            number=number,
            custom_name=input_custom_name(
                self.coordinator.config_entry.options,
                number,
            ),
        )

    def _name_after_output(self, number: int) -> None:
        """Name the entity after the output it belongs to."""
        self._name_after_port(
            placeholder=PLACEHOLDER_OUTPUT,
            number=number,
            custom_name=output_custom_name(
                self.coordinator.config_entry.options,
                number,
            ),
        )

    def _name_after_port(
        self,
        placeholder: str,
        number: int,
        custom_name: str | None,
    ) -> None:
        """Fill the placeholders of the entity name.

        A port without a user defined name keeps the default name, which only
        knows the port number. As soon as a name is configured, the variant of
        the name that also shows it is used.
        """
        placeholders = {placeholder: str(number)}

        if custom_name and (translation_key := self._attr_translation_key):
            self._attr_translation_key = (
                f"{translation_key}{TRANSLATION_KEY_NAMED_SUFFIX}"
            )
            placeholders[PLACEHOLDER_NAME] = custom_name

        self._attr_translation_placeholders = placeholders
