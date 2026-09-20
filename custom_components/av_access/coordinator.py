"""Data update coordinator for the AV Access HDMI matrix integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.const import CONF_SCAN_INTERVAL
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
from .const import DEFAULT_SCAN_INTERVAL

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
        scan_interval = config_entry.data.get(
            CONF_SCAN_INTERVAL,
            DEFAULT_SCAN_INTERVAL,
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="AV Access Matrix",
            update_interval=timedelta(seconds=scan_interval),
        )

        self.client = client

        # The static device information is read once while setting up the entry.
        self.device_info = device_info

        # The input whose EDID and HDCP are read during the next poll.
        self._next_input = 1

        # Set while the state a command confirmed is published, so entities can
        # tell a change they caused from a change made at the device.
        self._command_update = False

    @property
    def command_update(self) -> bool:
        """Return whether the current update belongs to a command."""
        return self._command_update

    async def async_refresh_after_command(self) -> None:
        """Refresh the state after a command."""
        await self.async_request_refresh()

    async def async_set_output(self, output: int, input_number: int) -> None:
        """Route an HDMI input to an output."""
        current_input = self.data["outputs"].get(str(output))

        # Skip sending the command if the output is already set to the desired input.
        if current_input == input_number:
            _LOGGER.debug("Output %d is already set to input %d", output, input_number)
            return

        confirmed = await self.client.async_set_output(output, input_number)

        self._async_apply("outputs", str(output), confirmed)

        await self.async_refresh_after_command()

    async def async_set_edid(self, input_number: int, edid: int) -> None:
        """Set the EDID of an HDMI input."""
        current_edid = self.data["edid"].get(str(input_number))

        # Skip sending the command if the EDID is already set to the desired value.
        if current_edid == edid:
            _LOGGER.debug("EDID for input %d is already set to %s", input_number, edid)
            return

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

        self._command_update = True

        try:
            self.async_set_updated_data(
                {
                    **self.data,
                    section: {**self.data[section], port: value},  # type: ignore[literal-required]
                }
            )

        finally:
            self._command_update = False

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

        The matrix answers one command at a time, so reading everything on every
        poll would keep the device busy permanently. The routing is read on
        every poll because it changes for every output at once, while EDID and
        HDCP are read for one input per poll. Changes made at the front panel or
        with the remote control therefore show up after one full rotation at the
        latest.
        """
        if self.data is None:
            return await self.client.async_get_status()

        outputs = await self.client.async_get_routing()

        edid = dict(self.data["edid"])
        hdcp = dict(self.data["hdcp"])

        input_number = self._next_input
        input_count = max(self.device_info.input_count, 1)

        if input_number > input_count:
            input_number = 1

        self._next_input = input_number % input_count + 1

        port = str(input_number)

        # Only ports the matrix already reported have entities, so no unknown
        # port is queried and no entity appears after the setup.
        if port in edid:
            value = await self.client.async_get_input_edid(input_number)

            if value is not None:
                edid[port] = value

        if port in hdcp:
            state = await self.client.async_get_input_hdcp(input_number)

            if state is not None:
                hdcp[port] = state

        return {
            "outputs": outputs,
            "edid": edid,
            "hdcp": hdcp,
        }
