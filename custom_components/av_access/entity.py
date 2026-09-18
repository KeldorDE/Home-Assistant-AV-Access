"""Base entity for the AV Access HDMI matrix integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    PLACEHOLDER_INPUT,
    PLACEHOLDER_NAME,
    PLACEHOLDER_OUTPUT,
    TRANSLATION_KEY_NAMED_SUFFIX,
)
from .coordinator import AVAccessCoordinator
from .labels import input_custom_name, output_custom_name


class AVAccessEntity(CoordinatorEntity[AVAccessCoordinator]):
    """Base entity for AV Access HDMI matrix entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AVAccessCoordinator) -> None:
        """Initialize the AV Access HDMI matrix entity."""
        super().__init__(coordinator)

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
