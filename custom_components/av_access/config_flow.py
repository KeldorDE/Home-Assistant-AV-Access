"""Config flow for the AV Access HDMI Matrix integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AVAccessApiClient,
    AVAccessApiError,
    AVAccessDeviceInfo,
)
from .const import DEFAULT_NAME, DEFAULT_PORT, DOMAIN

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


class AVAccessConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AV Access HDMI Matrix."""

    VERSION = 1

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
