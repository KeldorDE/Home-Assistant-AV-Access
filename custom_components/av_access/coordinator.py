"""Data update coordinator for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    AVAccessApiClient,
    AVAccessApiError,
    AVAccessConnectionError,
    AVAccessDeviceInfo,
    AVAccessStatus,
)
from .const import UPDATE_INTERVAL

if TYPE_CHECKING:
    from . import AVAccessConfigEntry

_LOGGER = logging.getLogger(__name__)


class AVAccessCoordinator(DataUpdateCoordinator[AVAccessStatus]):
    """Coordinate data updates from the AV Access HDMI-Matrix Controller."""

    config_entry: AVAccessConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: AVAccessApiClient,
        config_entry: AVAccessConfigEntry,
        device_info: AVAccessDeviceInfo,
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

        # The static device information is read once while setting up the entry.
        self.device_info = device_info

    async def _async_update_data(self) -> AVAccessStatus:
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
