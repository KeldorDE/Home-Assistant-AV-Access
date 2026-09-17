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

            else:
                # Prevent the same controller from being configured twice.
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"HDMI-Matrix ({host})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(
                        CONF_PORT,
                        default=DEFAULT_PORT,
                    ): int,
                }
            ),
            errors=errors,
        )
