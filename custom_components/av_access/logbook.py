"""Logbook descriptions for the AV Access HDMI matrix integration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_EXTERNAL_CHANGE

# The logbook does not translate the descriptions of custom events, so the
# message is kept in English like the ones of the core integrations.
MESSAGE_EXTERNAL_CHANGE = "was changed at the matrix"


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    """Describe the events of the integration for the logbook."""

    @callback
    def async_describe_external_change(event: Event) -> dict[str, Any]:
        """Describe a change made at the front panel or with the remote."""
        return {
            "name": "AV Access",
            "message": MESSAGE_EXTERNAL_CHANGE,
            "entity_id": event.data.get(ATTR_ENTITY_ID),
        }

    async_describe_event(
        DOMAIN,
        EVENT_EXTERNAL_CHANGE,
        async_describe_external_change,
    )
