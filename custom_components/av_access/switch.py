"""Switch platform for the AV Access HDMI matrix integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AVAccessConfigEntry
from .const import (
    TRANSLATION_KEY_INPUT_HDCP,
    TRANSLATION_KEY_OUTPUT_AUDIO_MUTE,
    TRANSLATION_KEY_OUTPUT_CEC_AUTO,
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
    """Set up AV Access HDMI matrix switch entities."""
    coordinator = entry.runtime_data
    data = coordinator.data
    device = coordinator.device_info

    # A matrix that does not support a setting reports it for no port at all.
    # One that does gets an entity on every port, even if the answer of a
    # single port got lost during the setup. The next poll fills in its value.
    inputs = range(1, device.input_count + 1)
    outputs = range(1, device.output_count + 1)

    if data["hdcp"]:
        async_add_entities(
            AVAccessHdcpSwitch(
                coordinator=coordinator,
                input_number=input_number,
            )
            for input_number in inputs
        )

    if data["audio_mute"]:
        async_add_entities(
            AVAccessAudioMuteSwitch(
                coordinator=coordinator,
                output=output,
            )
            for output in outputs
        )

    if data["cec_auto"]:
        async_add_entities(
            AVAccessCecAutoSwitch(
                coordinator=coordinator,
                output=output,
            )
            for output in outputs
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
            context=self._context,
        )


class AVAccessAudioMuteSwitch(AVAccessEntity, SwitchEntity):
    """Mute or unmute the audio of a matrix output."""

    _attr_translation_key = TRANSLATION_KEY_OUTPUT_AUDIO_MUTE
    _reports_external_change = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the audio mute switch."""
        super().__init__(coordinator)

        self._output = output

        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_audio_mute"
        )

        self._name_after_output(output)

    @property
    def is_on(self) -> bool | None:
        """Return whether the output audio is muted."""
        return self.coordinator.data["audio_mute"].get(self._output)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute the output audio."""
        await self.coordinator.async_set_audio_mute(
            self._output, True, context=self._context
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute the output audio."""
        await self.coordinator.async_set_audio_mute(
            self._output, False, context=self._context
        )


class AVAccessCecAutoSwitch(AVAccessEntity, SwitchEntity):
    """Enable or disable the automatic CEC power function of a matrix output.

    While it is on, the matrix powers the sink of the output off over CEC once
    the output has been without an active signal for the configured delay.
    """

    _attr_translation_key = TRANSLATION_KEY_OUTPUT_CEC_AUTO
    _reports_external_change = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AVAccessCoordinator,
        output: int,
    ) -> None:
        """Initialize the automatic CEC power switch."""
        super().__init__(coordinator)

        self._output = output

        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_output_{output}_cec_auto"
        )

        self._name_after_output(output)

    @property
    def is_on(self) -> bool | None:
        """Return whether the automatic CEC power function is enabled."""
        return self.coordinator.data["cec_auto"].get(self._output)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the automatic CEC power function."""
        await self.coordinator.async_set_cec_auto(
            self._output, True, context=self._context
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the automatic CEC power function."""
        await self.coordinator.async_set_cec_auto(
            self._output, False, context=self._context
        )
