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
    AVAccessConnectionError,
)
from .const import DEFAULT_PORT, DOMAIN

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
) -> None:
    """Validate that the controller can be reached."""

    session = async_get_clientsession(hass)

    client = AVAccessApiClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        session=session,
    )

    await client.get_status()


class AVAccessConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AV Access HDMI Matrix."""

    VERSION = 1

    async def _async_validate(
        self,
        user_input: dict[str, Any],
    ) -> dict[str, str]:
        """Validate the user input and return the errors to show, if any."""

        errors: dict[str, str] = {}

        try:
            await validate_input(self.hass, user_input)

        except AVAccessConnectionError:
            errors["base"] = "cannot_connect"

        except AVAccessApiError:
            errors["base"] = "cannot_connect"

        except Exception:
            _LOGGER.exception(
                "Unexpected error while connecting to AV Access HDMI Matrix Controller"
            )
            errors["base"] = "unknown"

        return errors

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial configuration step."""

        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]

            user_input[CONF_HOST] = host

            # Prevent the same controller from being configured twice.
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            errors = await self._async_validate(user_input)

            if not errors:
                return self.async_create_entry(
                    title=f"HDMI-Matrix ({host})",
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
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]

            user_input[CONF_HOST] = host

            unique_id = f"{host}:{port}"

            # The unique ID is derived from the connection details, so it changes
            # with them. Only a collision with another entry must be rejected.
            existing_entry = self.hass.config_entries.async_entry_for_domain_unique_id(
                DOMAIN,
                unique_id,
            )

            if (
                existing_entry is not None
                and existing_entry.entry_id != reconfigure_entry.entry_id
            ):
                return self.async_abort(reason="already_configured")

            errors = await self._async_validate(user_input)

            if not errors:
                await self.async_set_unique_id(unique_id)

                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    unique_id=unique_id,
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
