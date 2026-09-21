"""Data update coordinator for the AV Access HDMI matrix integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, TypeVar, cast

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
from .const import COMMAND_CONFIRM_TIMEOUT, DEFAULT_SCAN_INTERVAL

if TYPE_CHECKING:
    from . import AVAccessConfigEntry

_LOGGER = logging.getLogger(__name__)

# The values of the states the matrix reports for a port.
_ValueT = TypeVar("_ValueT", int, bool)


@dataclass
class _PendingCommand:
    """A value the matrix confirmed for a command but has not reported yet."""

    value: int | bool
    expires_at: float


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

        # The values commands confirmed, kept until the matrix reports them.
        self._pending: dict[tuple[str, str], _PendingCommand] = {}

    @property
    def command_update(self) -> bool:
        """Return whether the current update belongs to a command."""
        return self._command_update

    async def async_set_output(self, output: int, input_number: int) -> None:
        """Route an HDMI input to an output."""
        current_input = self.data["outputs"].get(str(output))

        # Skip sending the command if the output is already set to the desired input.
        if current_input == input_number:
            _LOGGER.debug("Output %d is already set to input %d", output, input_number)
            return

        confirmed = await self.client.async_set_output(output, input_number)

        # The matrix confirms the applied value, which is published right away,
        # and the routing is read on every poll, so no extra refresh is needed.
        self._async_apply("outputs", str(output), confirmed)

    async def async_set_edid(self, input_number: int, edid: int) -> None:
        """Set the EDID of an HDMI input."""
        current_edid = self.data["edid"].get(str(input_number))

        # Skip sending the command if the EDID is already set to the desired value.
        if current_edid == edid:
            _LOGGER.debug("EDID for input %d is already set to %s", input_number, edid)
            return

        confirmed = await self.client.async_set_edid(input_number, edid)

        self._async_apply("edid", str(input_number), confirmed)

    async def async_set_hdcp(self, input_number: int, enabled: bool) -> None:
        """Switch HDCP support of an HDMI input."""
        current_hdcp = self.data["hdcp"].get(str(input_number))

        # Skip sending the command if HDCP is already in the desired state.
        if current_hdcp == enabled:
            _LOGGER.debug(
                "HDCP for input %d is already %s",
                input_number,
                "on" if enabled else "off",
            )
            return

        confirmed = await self.client.async_set_hdcp(input_number, enabled)

        self._async_apply("hdcp", str(input_number), confirmed)

    @callback
    def _async_apply(self, section: str, port: str, value: int | bool) -> None:
        """Publish the state the matrix confirmed for a command.

        The matrix answers every command with the value it applied, so an entity
        does not have to wait for the next poll. Only the routing is read on
        every poll, which makes this the timely update for EDID and HDCP.
        """
        if self.data is None:
            return

        # A poll that started before the command still reports the previous
        # value, so the confirmed one is kept until the matrix reports it.
        self._pending[(section, port)] = _PendingCommand(
            value=value,
            expires_at=self.hass.loop.time() + COMMAND_CONFIRM_TIMEOUT,
        )

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

    @callback
    def _async_confirm(self, section: str, port: str, value: _ValueT) -> _ValueT:
        """Return the value to publish for a value read from the matrix.

        Ignore stale poll results while a command awaits confirmation to
        prevent false external changes. Once the command is no longer recent,
        accept the matrix's reported value.
        """
        key = (section, port)
        pending = self._pending.get(key)

        if pending is None:
            return value

        if pending.value == value:
            del self._pending[key]
            return value

        if pending.expires_at <= self.hass.loop.time():
            del self._pending[key]

            _LOGGER.debug(
                "Matrix reports %s for %s %s instead of the commanded %s",
                value,
                section,
                port,
                pending.value,
            )

            return value

        return cast(_ValueT, pending.value)

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

        The matrix processes commands sequentially, so polling all values would
        keep it busy. Routing is checked every poll, while EDID and HDCP rotate
        through one input per poll. External changes are detected within one rotation.
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

        # The values read from the matrix during this poll.
        read: list[tuple[str, str]] = [
            ("outputs", output_port) for output_port in outputs
        ]

        # Only ports the matrix already reported have entities, so no unknown
        # port is queried and no entity appears after the setup.
        if port in edid:
            value = await self.client.async_get_input_edid(input_number)

            if value is not None:
                edid[port] = value
                read.append(("edid", port))

        if port in hdcp:
            state = await self.client.async_get_input_hdcp(input_number)

            if state is not None:
                hdcp[port] = state
                read.append(("hdcp", port))

        status: AVAccessStatus = {
            "outputs": outputs,
            "edid": edid,
            "hdcp": hdcp,
        }

        # Reading the whole state takes several seconds, in which a command can
        # change it. The values are therefore compared with the pending ones
        # after the last read, so a value read before a command does not undo
        # it.
        read_keys = set(read)

        for section, read_port in read:
            values = status[section]  # type: ignore[literal-required]
            values[read_port] = self._async_confirm(
                section,
                read_port,
                values[read_port],
            )

        # EDID and HDCP are read for a single input per poll, so a command that
        # changes another input is only carried forward from a snapshot taken
        # when the poll began. A poll that started before the command holds the
        # previous value in that snapshot and would overwrite the confirmed one
        # when its result is published. The confirmed value therefore stands
        # for every port not read this poll until a later poll reads and
        # reconciles it.
        for (section, port), pending in self._pending.items():
            if (section, port) in read_keys:
                continue

            status[section][port] = pending.value  # type: ignore[literal-required]

        return status
