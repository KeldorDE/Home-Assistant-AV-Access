"""Data update coordinator for the AV Access HDMI matrix integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .client import (
    AVAccessClient,
    AVAccessConnectionError,
    AVAccessDeviceInfo,
    AVAccessError,
    AVAccessStatus,
)
from .const import FULL_SYNC_INTERVAL, UPDATE_INTERVAL

if TYPE_CHECKING:
    from . import AVAccessConfigEntry

_LOGGER = logging.getLogger(__name__)


class AVAccessCoordinator(DataUpdateCoordinator[AVAccessStatus]):
    """Poll the state of the AV Access HDMI matrix."""

    config_entry: AVAccessConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: AVAccessClient,
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

        self._next_full_sync = 0.0

    async def async_refresh_after_command(self) -> None:
        """Refresh the state after a command."""
        await self.async_request_refresh()

    async def async_set_output(self, output: int, input_number: int) -> None:
        """Route an HDMI input to an output."""
        confirmed = await self.client.async_set_output(output, input_number)

        self._async_apply("outputs", str(output), confirmed)

        await self.async_refresh_after_command()

    async def async_set_edid(self, input_number: int, edid: int) -> None:
        """Set the EDID of an HDMI input."""
        confirmed = await self.client.async_set_edid(input_number, edid)

        self._async_apply("edid", str(input_number), confirmed)

        await self.async_refresh_after_command()

    async def async_set_hdcp(self, input_number: int, enabled: bool) -> None:
        """Switch HDCP support of an HDMI input."""
        confirmed = await self.client.async_set_hdcp(input_number, enabled)

        self._async_apply("hdcp", str(input_number), confirmed)

        await self.async_refresh_after_command()

    @callback
    def _async_apply(self, section: str, port: str, value: int | bool) -> None:
        """Publish the state the matrix confirmed for a command.

        The matrix answers every command with the value it applied, so an entity
        does not have to wait for the next poll. Only the routing is read on
        every poll, which makes this the timely update for EDID and HDCP.
        """
        if self.data is None:
            return

        self.async_set_updated_data(
            {
                **self.data,
                section: {**self.data[section], port: value},  # type: ignore[literal-required]
            }
        )

    async def _async_update_data(self) -> AVAccessStatus:
        """Fetch the latest state of the matrix."""
        try:
            return await self._async_fetch_status()

        except AVAccessConnectionError as err:
            raise UpdateFailed(
                f"Unable to connect to the AV Access matrix: {err}"
            ) from err

        except AVAccessError as err:
            raise UpdateFailed(
                f"Error communicating with the AV Access matrix: {err}"
            ) from err

    async def _async_fetch_status(self) -> AVAccessStatus:
        """Read the state, sparing the matrix the commands that rarely change.

        Reading EDID and HDCP costs one command per input, and every command
        occupies the matrix for at least a second. The routing is the only value
        that also changes at the front panel, so it is the only one that is
        polled continuously.
        """
        now = self.hass.loop.time()

        if self.data is None or now >= self._next_full_sync:
            status = await self.client.async_get_status()

            self._next_full_sync = now + FULL_SYNC_INTERVAL

            return status

        return {
            **self.data,
            "outputs": await self.client.async_get_routing(),
        }
