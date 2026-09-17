"""Config flow for the AV Access HDMI Matrix integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AVAccessApiClient,
    AVAccessApiError,
    AVAccessDeviceInfo,
)
from .const import (
    CONF_INPUT_LABELS,
    CONF_OUTPUT_LABELS,
    DEFAULT_INPUT_COUNT,
    DEFAULT_NAME,
    DEFAULT_OUTPUT_COUNT,
    DEFAULT_PORT,
    DOMAIN,
)
from .labels import (
    has_duplicates,
    input_label_key,
    input_options,
    output_label_key,
    stored_labels,
)

_LOGGER = logging.getLogger(__name__)

STEP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(
            CONF_PORT,
            default=DEFAULT_PORT,
        ): int,
    }
)


async def validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> AVAccessDeviceInfo:
    """Validate that the controller can be reached and identify the matrix."""

    session = async_get_clientsession(hass)

    client = AVAccessApiClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        session=session,
    )

    return await client.get_device_info()


def _labels_schema(keys: list[str], stored: dict[str, str]) -> vol.Schema:
    """Return a schema with one optional text field per port."""

    return vol.Schema(
        {
            vol.Optional(
                key,
                description={"suggested_value": stored.get(key, "")},
            ): str
            for key in keys
        }
    )


def _merge_labels(
    stored: dict[str, str],
    user_input: dict[str, Any],
    keys: list[str],
) -> dict[str, str]:
    """Apply the submitted names, keeping names of ports not shown in the form."""

    merged = dict(stored)

    for key in keys:
        value = user_input.get(key)
        name = value.strip() if isinstance(value, str) else ""

        if name:
            merged[key] = name
        else:
            merged.pop(key, None)

    return merged


class AVAccessConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AV Access HDMI Matrix."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AVAccessOptionsFlow:
        """Return the options flow that names the ports."""
        return AVAccessOptionsFlow()

    async def _async_validate(
        self,
        user_input: dict[str, Any],
    ) -> tuple[AVAccessDeviceInfo | None, dict[str, str]]:
        """Validate the user input and return the device info and any errors."""

        errors: dict[str, str] = {}

        try:
            device_info = await validate_input(self.hass, user_input)

        except AVAccessApiError:
            # AVAccessConnectionError is a subclass and handled the same way.
            errors["base"] = "cannot_connect"

        except Exception:
            _LOGGER.exception(
                "Unexpected error while connecting to AV Access HDMI Matrix Controller"
            )
            errors["base"] = "unknown"

        else:
            return device_info, errors

        return None, errors

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial configuration step."""

        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()

            device_info, errors = await self._async_validate(user_input)

            if device_info is not None:
                # The matrix reports its own identity, so the same device cannot
                # be added twice under different connection details.
                await self.async_set_unique_id(device_info.unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=device_info.model or DEFAULT_NAME,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle reconfiguration of an existing controller."""

        reconfigure_entry = self._get_reconfigure_entry()

        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()

            device_info, errors = await self._async_validate(user_input)

            if device_info is not None:
                # Reconfiguration must not silently point the entry at a
                # different matrix.
                await self.async_set_unique_id(device_info.unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_device")

                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_DATA_SCHEMA,
                reconfigure_entry.data,
            ),
            errors=errors,
        )


class AVAccessOptionsFlow(config_entries.OptionsFlowWithReload):
    """Let the user name the inputs and outputs of the matrix."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the port naming step."""

        entry = self.config_entry

        # The port counts are only known once the controller has been queried.
        runtime_data = getattr(entry, "runtime_data", None)

        if runtime_data is None:
            input_count = DEFAULT_INPUT_COUNT
            output_count = DEFAULT_OUTPUT_COUNT
        else:
            input_count = runtime_data.device_info.input_count
            output_count = runtime_data.device_info.output_count

        input_keys = [input_label_key(number) for number in range(1, input_count + 1)]
        output_keys = [
            output_label_key(number) for number in range(1, output_count + 1)
        ]

        stored_inputs = stored_labels(entry.options, CONF_INPUT_LABELS)
        stored_outputs = stored_labels(entry.options, CONF_OUTPUT_LABELS)

        errors: dict[str, str] = {}

        if user_input is not None:
            options = {
                CONF_INPUT_LABELS: _merge_labels(
                    stored_inputs,
                    user_input.get(CONF_INPUT_LABELS, {}),
                    input_keys,
                ),
                CONF_OUTPUT_LABELS: _merge_labels(
                    stored_outputs,
                    user_input.get(CONF_OUTPUT_LABELS, {}),
                    output_keys,
                ),
            }

            # Two inputs sharing an option would make a selection ambiguous.
            if has_duplicates(input_options(options, input_count)):
                errors["base"] = "duplicate_labels"

            else:
                return self.async_create_entry(data=options)

            stored_inputs = options[CONF_INPUT_LABELS]
            stored_outputs = options[CONF_OUTPUT_LABELS]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INPUT_LABELS): section(
                        _labels_schema(input_keys, stored_inputs),
                    ),
                    vol.Required(CONF_OUTPUT_LABELS): section(
                        _labels_schema(output_keys, stored_outputs),
                    ),
                }
            ),
            errors=errors,
        )
