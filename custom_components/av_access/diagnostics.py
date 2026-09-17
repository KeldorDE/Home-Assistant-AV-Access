"""Diagnostics support for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_URL
from homeassistant.core import HomeAssistant

from . import AVAccessConfigEntry

# Addresses identify the installation and are not needed to debug an issue.
# CONF_URL is no longer configurable but may still be present in older entries.
TO_REDACT = {
    CONF_HOST,
    CONF_URL,
    "configuration_url",
    "gateway",
    "ip_address",
    "netmask",
    "unique_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: AVAccessConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    device_info = asdict(coordinator.device_info)

    if coordinator.device_info.updated_at is not None:
        device_info["updated_at"] = coordinator.device_info.updated_at.isoformat()

    return async_redact_data(
        {
            "entry_data": dict(entry.data),
            "entry_options": dict(entry.options),
            "device_info": device_info,
            "status": coordinator.data,
        },
        TO_REDACT,
    )
