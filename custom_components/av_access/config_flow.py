"""Config flow for the AV Access HDMI Matrix integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .client import (
    AVAccessClient,
    AVAccessDeviceInfo,
    AVAccessError,
    CommandPriority,
    is_same_device,
    ports_from_model,
)
from .const import (
    CONF_EDID_LABELS,
    CONF_EDID_OPTIONS,
    CONF_EDID_OPTIONS_SOURCE,
    CONF_INPUT_LABELS,
    CONF_OUTPUT_LABELS,
    DEFAULT_INPUT_COUNT,
    DEFAULT_NAME,
    DEFAULT_OUTPUT_COUNT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EDID_SOURCE_DEVICE,
    MAX_PORT,
    MAX_SCAN_INTERVAL,
    MIN_PORT,
    MIN_SCAN_INTERVAL,
)
from .edid import async_read_edid_options
from .labels import (
    device_edid_options,
    edid_label_key,
    edid_options,
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
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=DEFAULT_SCAN_INTERVAL,
        ): vol.All(
            NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Coerce(int),
        ),
    }
)


async def validate_input(data: dict[str, Any]) -> AVAccessDeviceInfo:
    """Validate that the matrix can be reached and identify it."""
    client = AVAccessClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
    )

    # Somebody waits for the dialog, so the validation goes ahead of the
    # polling of an entry that already talks to the same matrix.
    return await client.async_get_device_info(priority=CommandPriority.USER)


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


def _edid_fields(descriptions: Mapping[int, str]) -> dict[str, int]:
    """Return the form field of every EDID, mapped to the EDID value.

    The list comes from the matrix, so there is no translation a field could be
    labelled with. A field without one is labelled with its key, which is why
    the description of the matrix serves as the key.
    """
    fields: dict[str, int] = {}

    for value, description in descriptions.items():
        field = description if description not in fields else f"{description} ({value})"
        fields[field] = value

    return fields


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

    async def _async_edid_data(
        self,
        host: str,
        previous: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the entry data describing the EDIDs the matrix offers."""
        options, source = await async_read_edid_options(self.hass, host)

        # A list the matrix once provided is worth more than the built-in one,
        # so it survives a reconfiguration during which the web interface of
        # the matrix cannot be read.
        if (
            source != EDID_SOURCE_DEVICE
            and previous is not None
            and previous.get(CONF_EDID_OPTIONS_SOURCE) == EDID_SOURCE_DEVICE
            and previous.get(CONF_EDID_OPTIONS)
        ):
            options = previous[CONF_EDID_OPTIONS]
            source = EDID_SOURCE_DEVICE

        return {
            CONF_EDID_OPTIONS: options,
            CONF_EDID_OPTIONS_SOURCE: source,
        }

    async def _async_validate(
        self,
        user_input: dict[str, Any],
    ) -> tuple[AVAccessDeviceInfo | None, dict[str, str]]:
        """Validate the user input and return the device info and any errors."""
        errors: dict[str, str] = {}

        # A port outside the valid range can never be reached, which would only
        # surface as a failed connection. Checking it here names the field.
        if not MIN_PORT <= user_input[CONF_PORT] <= MAX_PORT:
            errors[CONF_PORT] = "invalid_port"

            return None, errors

        try:
            device_info = await validate_input(user_input)

        except AVAccessError:
            # A matrix that answers with something unexpected is just as
            # unusable as one that cannot be reached at all.
            errors["base"] = "cannot_connect"

        except Exception:
            _LOGGER.exception(
                "Unexpected error while connecting to the AV Access HDMI matrix"
            )
            errors["base"] = "unknown"

        else:
            # Anything that listens on the port answers something, for example
            # an SSH server or a router. Only a matrix names a model that
            # carries its port layout, such as the 44 of the 4KMX44-H2, in its
            # version or in its welcome line.
            if ports_from_model(device_info.model) is not None:
                return device_info, errors

            errors["base"] = "unsupported_device"

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
                    data={
                        **user_input,
                        **await self._async_edid_data(user_input[CONF_HOST]),
                    },
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
        """Handle reconfiguration of an existing matrix."""
        reconfigure_entry = self._get_reconfigure_entry()

        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()

            device_info, errors = await self._async_validate(user_input)

            if device_info is not None:
                # The address may legitimately change, for example after a new
                # DHCP lease, so only the model decides whether the entry still
                # describes the same matrix.
                if not is_same_device(
                    reconfigure_entry.unique_id,
                    device_info.model,
                    reconfigure_entry.data[CONF_HOST],
                ):
                    return self.async_abort(reason="wrong_device")

                # The ID follows the new address, which keeps a second entry
                # from being created for the same matrix later on.
                existing_entry = await self.async_set_unique_id(device_info.unique_id)

                if (
                    existing_entry is not None
                    and existing_entry.entry_id != reconfigure_entry.entry_id
                ):
                    return self.async_abort(reason="already_configured")

                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data={
                        **user_input,
                        **await self._async_edid_data(
                            user_input[CONF_HOST],
                            reconfigure_entry.data,
                        ),
                    },
                    unique_id=device_info.unique_id,
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
    """Let the user name the inputs, outputs and EDIDs of the matrix."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the naming step."""
        entry = self.config_entry

        # The port counts are only known once the matrix has been queried.
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
        stored_edids = stored_labels(entry.options, CONF_EDID_LABELS)

        edid_fields = _edid_fields(device_edid_options(entry.data))
        edid_keys = [edid_label_key(value) for value in edid_fields.values()]

        errors: dict[str, str] = {}

        if user_input is not None:
            edid_input = user_input.get(CONF_EDID_LABELS, {})

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
                CONF_EDID_LABELS: _merge_labels(
                    stored_edids,
                    {
                        edid_label_key(value): edid_input.get(field)
                        for field, value in edid_fields.items()
                    },
                    edid_keys,
                ),
            }

            # Two inputs or two EDIDs sharing an option would make a selection
            # ambiguous.
            if has_duplicates(input_options(options, input_count)) or has_duplicates(
                edid_options(entry.data, options)
            ):
                errors["base"] = "duplicate_labels"

            else:
                return self.async_create_entry(data=options)

            stored_inputs = options[CONF_INPUT_LABELS]
            stored_outputs = options[CONF_OUTPUT_LABELS]
            stored_edids = options[CONF_EDID_LABELS]

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
                    # The list of EDIDs is long and rarely renamed, so its
                    # section starts collapsed.
                    vol.Required(CONF_EDID_LABELS): section(
                        vol.Schema(
                            {
                                vol.Optional(
                                    field,
                                    description={
                                        "suggested_value": stored_edids.get(
                                            edid_label_key(value), ""
                                        )
                                    },
                                ): str
                                for field, value in edid_fields.items()
                            }
                        ),
                        {"collapsed": True},
                    ),
                }
            ),
            errors=errors,
        )
