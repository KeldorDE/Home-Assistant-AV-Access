"""Data update coordinator for the AV Access HDMI matrix integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Literal, TypeVar, cast

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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

# The sections of the state, matching the keys of AVAccessStatus.
_Section = Literal["outputs", "edid", "hdcp", "audio_mute", "cec_auto", "cec_delay"]

# The sections whose values are boolean, which the reconciliation has to know
# to keep the writes to the status type-safe.
_BOOL_SECTIONS: tuple[_Section, ...] = ("hdcp", "audio_mute", "cec_auto")


@dataclass
class _PendingCommand:
    """A value the matrix confirmed for a command but has not reported yet."""

    value: int | bool
    expires_at: float


class _PendingState:
    """Track values commands confirmed until the matrix reports them.

    The matrix answers every command with the value it applied, so an entity
    does not have to wait for the next poll. A poll that started before the
    command still reports the previous value, so the confirmed one wins until
    the matrix reports it or the confirmation window elapses. Keeping this in a
    small object of its own makes the reconciliation testable in isolation.
    """

    def __init__(self, time: Callable[[], float], timeout: float) -> None:
        """Initialize the pending state with a clock and a confirmation window."""
        self._time = time
        self._timeout = timeout
        self._pending: dict[tuple[_Section, int], _PendingCommand] = {}

    def record(self, section: _Section, port: int, value: int | bool) -> None:
        """Remember the value a command confirmed for a port."""
        self._pending[(section, port)] = _PendingCommand(
            value=value,
            expires_at=self._time() + self._timeout,
        )

    def confirm(self, section: _Section, port: int, value: _ValueT) -> _ValueT:
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

        if pending.expires_at <= self._time():
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

    def carry(
        self,
        status: AVAccessStatus,
        read_keys: set[tuple[_Section, int]],
    ) -> None:
        """Keep confirmed values on ports that were not read this poll.

        EDID and HDCP are read for a single input per poll, and audio mute and
        the CEC settings are read for a single output per poll. A command that
        changes another port
        is only carried forward from a snapshot taken when the poll began. A
        poll that started before the command holds the previous value in that
        snapshot and would overwrite the confirmed one when its result is
        published. The confirmed value therefore stands for every port not read
        this poll until a later poll reads and reconciles it. Once its window has
        elapsed the pending value is dropped, so a change made at the matrix is
        no longer masked.
        """
        now = self._time()
        expired: list[tuple[_Section, int]] = []

        for key, pending in self._pending.items():
            if key in read_keys:
                continue

            if pending.expires_at <= now:
                expired.append(key)
                continue

            section, port = key

            # The value type differs per section, so narrow before assigning to
            # keep the write type-safe without ignoring the checker.
            if section in _BOOL_SECTIONS:
                status[section][port] = cast(bool, pending.value)
            else:
                status[section][port] = cast(int, pending.value)

        for key in expired:
            del self._pending[key]


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
        # The output whose audio mute state is read during the next poll.
        self._next_output = 1

        # Set while the state a command confirmed is published, so entities can
        # tell a change they caused from a change made at the device.
        self._command_update = False

        # The values commands confirmed, kept until the matrix reports them.
        self._pending = _PendingState(
            time=self.hass.loop.time,
            timeout=COMMAND_CONFIRM_TIMEOUT,
        )

    @property
    def command_update(self) -> bool:
        """Return whether the current update belongs to a command."""
        return self._command_update

    async def async_set_output(self, output: int, input_number: int) -> None:
        """Route an HDMI input to an output."""
        current_input = self.data["outputs"].get(output)

        # Skip sending the command if the output is already set to the desired input.
        if current_input == input_number:
            _LOGGER.debug("Output %d is already set to input %d", output, input_number)
            return

        confirmed = await self.client.async_set_output(output, input_number)

        # The matrix confirms the applied value, which is published right away,
        # and the routing is read on every poll, so no extra refresh is needed.
        self._async_apply("outputs", output, confirmed)

    async def async_set_edid(self, input_number: int, edid: int) -> None:
        """Set the EDID of an HDMI input."""
        current_edid = self.data["edid"].get(input_number)

        # Skip sending the command if the EDID is already set to the desired value.
        if current_edid == edid:
            _LOGGER.debug("EDID for input %d is already set to %s", input_number, edid)
            return

        confirmed = await self.client.async_set_edid(input_number, edid)

        self._async_apply("edid", input_number, confirmed)

    async def async_set_hdcp(self, input_number: int, enabled: bool) -> None:
        """Switch HDCP support of an HDMI input."""
        current_hdcp = self.data["hdcp"].get(input_number)

        # Skip sending the command if HDCP is already in the desired state.
        if current_hdcp == enabled:
            _LOGGER.debug(
                "HDCP for input %d is already %s",
                input_number,
                "on" if enabled else "off",
            )
            return

        confirmed = await self.client.async_set_hdcp(input_number, enabled)

        self._async_apply("hdcp", input_number, confirmed)

    async def async_set_audio_mute(self, output: int, muted: bool) -> None:
        """Set the audio mute state of an HDMI output."""
        current_mute = self.data["audio_mute"].get(output)

        if current_mute == muted:
            _LOGGER.debug(
                "Audio for output %d is already %s",
                output,
                "muted" if muted else "unmuted",
            )
            return

        confirmed = await self.client.async_set_audio_mute(output, muted)

        self._async_apply("audio_mute", output, confirmed)

    async def async_set_cec_auto(self, output: int, enabled: bool) -> None:
        """Switch the automatic CEC power function of an HDMI output."""
        current_auto = self.data["cec_auto"].get(output)

        if current_auto == enabled:
            _LOGGER.debug(
                "Automatic CEC power for output %d is already %s",
                output,
                "on" if enabled else "off",
            )
            return

        confirmed = await self.client.async_set_cec_auto(output, enabled)

        self._async_apply("cec_auto", output, confirmed)

    async def async_set_cec_delay(self, output: int, minutes: int) -> None:
        """Set the automatic CEC power off delay of an HDMI output."""
        current_delay = self.data["cec_delay"].get(output)

        if current_delay == minutes:
            _LOGGER.debug(
                "CEC power off delay for output %d is already %d minutes",
                output,
                minutes,
            )
            return

        confirmed = await self.client.async_set_cec_delay(output, minutes)

        self._async_apply("cec_delay", output, confirmed)

    async def async_set_cec_power(self, output: int, power_on: bool) -> None:
        """Power the sink of an HDMI output on or off over CEC.

        The matrix does not report the power state of a sink, so there is no
        state to publish and nothing to reconcile with a later poll.
        """
        await self.client.async_set_cec_power(output, power_on)

    @callback
    def _async_apply(self, section: _Section, port: int, value: int | bool) -> None:
        """Publish the state the matrix confirmed for a command.

        The matrix answers every command with the value it applied, so an entity
        does not have to wait for the next poll. Only the routing is read on
        every poll, which makes this the timely update for the rotating states.
        """
        if self.data is None:
            return

        # A poll that started before the command still reports the previous
        # value, so the confirmed one is kept until the matrix reports it.
        self._pending.record(section, port, value)

        self._command_update = True

        try:
            self.async_set_updated_data(
                {
                    **self.data,
                    section: {**self.data[section], port: value},
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

        The matrix processes commands sequentially, so polling all values would
        keep it busy. Routing is checked every poll, while EDID and HDCP rotate
        through one input per poll and audio mute and the CEC settings rotate
        through one output per poll. External changes are detected within one
        rotation.
        """
        if self.data is None:
            return await self.client.async_get_status()

        outputs = await self.client.async_get_routing()

        edid = dict(self.data["edid"])
        hdcp = dict(self.data["hdcp"])
        audio_mute = dict(self.data["audio_mute"])
        cec_auto = dict(self.data["cec_auto"])
        cec_delay = dict(self.data["cec_delay"])

        # The values read from the matrix during this poll.
        read: list[tuple[_Section, int]] = [
            ("outputs", output_port) for output_port in outputs
        ]

        await self._async_read_input_states(edid, hdcp, read)
        await self._async_read_output_states(audio_mute, cec_auto, cec_delay, read)

        status: AVAccessStatus = {
            "outputs": outputs,
            "edid": edid,
            "hdcp": hdcp,
            "audio_mute": audio_mute,
            "cec_auto": cec_auto,
            "cec_delay": cec_delay,
        }

        # Reading the whole state takes several seconds, in which a command can
        # change it. The values are therefore compared with the pending ones
        # after the last read, so a value read before a command does not undo
        # it.
        read_keys = set(read)

        for section, read_port in read:
            values = status[section]
            values[read_port] = self._pending.confirm(
                section,
                read_port,
                values[read_port],
            )

        self._pending.carry(status, read_keys)

        return status

    async def _async_read_input_states(
        self,
        edid: dict[int, int],
        hdcp: dict[int, bool],
        read: list[tuple[_Section, int]],
    ) -> None:
        """Read the rotating states of the next input into the given values."""
        input_number = self._next_input
        input_count = max(self.device_info.input_count, 1)

        if input_number > input_count:
            input_number = 1

        self._next_input = input_number % input_count + 1

        # Only ports the matrix already reported have entities, so no unknown
        # port is queried and no entity appears after the setup.
        if input_number in edid:
            value = await self.client.async_get_input_edid(input_number)

            if value is not None:
                edid[input_number] = value
                read.append(("edid", input_number))

        if input_number in hdcp:
            state = await self.client.async_get_input_hdcp(input_number)

            if state is not None:
                hdcp[input_number] = state
                read.append(("hdcp", input_number))

    async def _async_read_output_states(
        self,
        audio_mute: dict[int, bool],
        cec_auto: dict[int, bool],
        cec_delay: dict[int, int],
        read: list[tuple[_Section, int]],
    ) -> None:
        """Read the rotating states of the next output into the given values."""
        output = self._next_output
        output_count = max(self.device_info.output_count, 1)

        if output > output_count:
            output = 1

        self._next_output = output % output_count + 1

        if output in audio_mute:
            muted = await self.client.async_get_output_audio_mute(output)

            if muted is not None:
                audio_mute[output] = muted
                read.append(("audio_mute", output))

        if output in cec_auto:
            enabled = await self.client.async_get_output_cec_auto(output)

            if enabled is not None:
                cec_auto[output] = enabled
                read.append(("cec_auto", output))

        if output in cec_delay:
            minutes = await self.client.async_get_output_cec_delay(output)

            if minutes is not None:
                cec_delay[output] = minutes
                read.append(("cec_delay", output))
