"""Data update coordinator for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    AVAccessApiClient,
    AVAccessApiError,
    AVAccessConnectionError,
)
from .const import UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class AVAccessCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate data updates from the AV Access HDMI-Matrix Controller."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: AVAccessApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="AV Access Matrix",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

        self.client = client

    async def _async_update_data(self) -> dict:
        """Fetch the latest matrix state."""
        try:
            return await self.client.get_status()

        except AVAccessConnectionError as err:
            raise UpdateFailed(
                f"Unable to connect to AV Access HDMI-Matrix Controller: {err}"
            ) from err

        except AVAccessApiError as err:
            raise UpdateFailed(
                f"Error communicating with AV Access HDMI-Matrix Controller: {err}"
            ) from err
