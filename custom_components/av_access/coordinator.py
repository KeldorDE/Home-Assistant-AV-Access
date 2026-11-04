"""Data update coordinator for the AV Access HDMI matrix integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
import logging
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    AVAccessClient,
    AVAccessConnectionError,
    AVAccessDeviceInfo,
    AVAccessError,
    AVAccessStatus,
)
from .const import (
    COMMAND_CONFIRM_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SETTINGS_POLL_INTERVAL,
)

if TYPE_CHECKING:
    from . import AVAccessConfigEntry

_LOGGER = logging.getLogger(__name__)

# The values of the states the matrix reports for a port.
_ValueT = TypeVar("_ValueT", int, bool)

# The value a command returns.
_ResultT = TypeVar("_ResultT")

# The sections of the state, matching the keys of AVAccessStatus.
_Section = Literal["outputs", "edid", "hdcp", "audio_mute", "cec_auto", "cec_delay"]

# The sections whose values are boolean, which the reconciliation has to know
# to keep the writes to the status type-safe.
_BOOL_SECTIONS: tuple[_Section, ...] = ("hdcp", "audio_mute", "cec_auto")


@dataclass
class _PendingCommand:
    """A value a command published but the matrix has not reported yet."""

    value: int | bool
    expires_at: float


class _PendingState:
    """Track the values of commands until the matrix reports them.

    A command publishes its value before it is sent and once more with the
    value the matrix confirmed, so an entity does not have to wait for the next
    poll. A poll that started before the command still reports the previous
    value, so the value of the command wins until the matrix reports it or the
    confirmation window elapses. Keeping this in a small object of its own
    makes the reconciliation testable in isolation.
    """

    def __init__(self, time: Callable[[], float], timeout: float) -> None:
        """Initialize the pending state with a clock and a confirmation window."""
        self._time = time
        self._timeout = timeout
        self._pending: dict[tuple[_Section, int], _PendingCommand] = {}

    def record(self, section: _Section, port: int, value: int | bool) -> None:
        """Remember the value a command published for a port."""
        self._pending[(section, port)] = _PendingCommand(
            value=value,
            expires_at=self._time() + self._timeout,
        )

    def discard(self, section: _Section, port: int) -> None:
        """Forget the value of a port, so the next poll is believed again."""
        self._pending.pop((section, port), None)

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
        """Keep the values of commands on ports that were not read this poll.

        A port whose value the matrix did not report this poll is carried
        forward from a snapshot taken when the poll began. A poll that started
        before a command holds the previous value in that snapshot and would
        overwrite the value of the command when its result is published. That
        value therefore stands for every port not read this poll until a later
        poll reads and reconciles it. Once its window has elapsed the pending
        value is dropped, so a change made at the matrix is no longer masked.
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

        # Set while the state of a command is published, so entities can tell a
        # change they caused from a change made at the device.
        self._command_update = False

        # The context of the service call whose command is being published, so
        # every entity the command changes names the same origin in the logbook.
        self._command_context: Context | None = None

        # The values commands confirmed, kept until the matrix reports them.
        self._pending = _PendingState(
            time=self.hass.loop.time,
            timeout=COMMAND_CONFIRM_TIMEOUT,
        )

        # The most recent command per port. Commands for the same port queue up
        # behind each other, so only the latest one may publish its outcome.
        self._latest_commands: dict[tuple[_Section, int], object] = {}

        # Loop time at which the last complete read of the settings started.
        self._settings_read_at: float | None = None

        # Set when the next poll has to read the settings regardless of the
        # interval, for example after a command whose outcome is unknown.
        self._settings_stale = False

    @property
    def command_update(self) -> bool:
        """Return whether the current update belongs to a command."""
        return self._command_update

    @property
    def command_context(self) -> Context | None:
        """Return the context of the service call the current update belongs to."""
        return self._command_context

    async def async_set_output(
        self,
        output: int,
        input_number: int,
        context: Context | None = None,
    ) -> None:
        """Route an HDMI input to an output."""
        await self._async_set_value(
            "outputs",
            output,
            input_number,
            partial(self.client.async_set_output, output, input_number),
            context,
        )

    async def async_set_edid(
        self,
        input_number: int,
        edid: int,
        context: Context | None = None,
    ) -> None:
        """Set the EDID of an HDMI input."""
        await self._async_set_value(
            "edid",
            input_number,
            edid,
            partial(self.client.async_set_edid, input_number, edid),
            context,
        )

    async def async_set_hdcp(
        self,
        input_number: int,
        enabled: bool,
        context: Context | None = None,
    ) -> None:
        """Switch HDCP support of an HDMI input."""
        await self._async_set_value(
            "hdcp",
            input_number,
            enabled,
            partial(self.client.async_set_hdcp, input_number, enabled),
            context,
        )

    async def async_set_audio_mute(
        self,
        output: int,
        muted: bool,
        context: Context | None = None,
    ) -> None:
        """Set the audio mute state of an HDMI output."""
        await self._async_set_value(
            "audio_mute",
            output,
            muted,
            partial(self.client.async_set_audio_mute, output, muted),
            context,
        )

    async def async_set_cec_auto(
        self,
        output: int,
        enabled: bool,
        context: Context | None = None,
    ) -> None:
        """Switch the automatic CEC power function of an HDMI output."""
        await self._async_set_value(
            "cec_auto",
            output,
            enabled,
            partial(self.client.async_set_cec_auto, output, enabled),
            context,
        )

    async def async_set_cec_delay(
        self,
        output: int,
        minutes: int,
        context: Context | None = None,
    ) -> None:
        """Set the automatic CEC power off delay of an HDMI output."""
        await self._async_set_value(
            "cec_delay",
            output,
            minutes,
            partial(self.client.async_set_cec_delay, output, minutes),
            context,
        )

    async def async_set_cec_power(self, output: int, power_on: bool) -> None:
        """Power the sink of an HDMI output on or off over CEC.

        The matrix does not report the power state of a sink, so there is no
        state to publish and nothing to reconcile with a later poll.
        """
        await self._async_command(self.client.async_set_cec_power(output, power_on))

    async def _async_set_value(
        self,
        section: _Section,
        port: int,
        value: int | bool,
        send: Callable[[], Coroutine[Any, Any, int | bool]],
        context: Context | None,
    ) -> None:
        """Publish a value right away, then send it to the matrix.

        A command may wait behind others, and a matrix that answers slowly
        takes up to the timeouts to confirm it. The requested value is
        therefore published before the command is sent, which lets the
        frontend react at once. The value the matrix confirms
        replaces it, and a failed command restores the previous value. A later
        command for the same port has the last word in both cases.
        """
        key = (section, port)
        previous = self.data[section].get(port)

        # Skip sending the command if the port already has the desired value.
        if previous == value:
            _LOGGER.debug(
                "The %s value of port %d already is %s, skipping the command",
                section,
                port,
                value,
            )
            return

        token = object()
        self._latest_commands[key] = token

        self._async_apply(section, port, value, context)

        try:
            confirmed = await self._async_command(send())

        # A command that is cancelled, for example by stopping the script that
        # issued it while it waits for its turn, leaves the value as unknown
        # as a failed one.
        except (HomeAssistantError, asyncio.CancelledError):
            if self._latest_commands.get(key) is token:
                del self._latest_commands[key]
                self._async_revert(section, port, previous, context)

            raise

        if self._latest_commands.get(key) is not token:
            return

        del self._latest_commands[key]

        if confirmed == value:
            # The confirmation restarts the window in which a poll that began
            # before the command was sent cannot undo the value.
            self._pending.record(section, port, confirmed)
        else:
            self._async_apply(section, port, confirmed, context)

    async def _async_command(self, command: Coroutine[Any, Any, _ResultT]) -> _ResultT:
        """Run a command of the user and report a failure to the frontend.

        A plain exception would only show up as an unexpected error with a
        traceback, while a Home Assistant error tells the user what went wrong.
        """
        try:
            return await command

        except AVAccessError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    @callback
    def _async_apply(
        self,
        section: _Section,
        port: int,
        value: int | bool,
        context: Context | None,
    ) -> None:
        """Publish the value of a command without waiting for the next poll.

        Only the routing is read on every poll, which makes this the timely
        update for the rotating states.
        """
        if self.data is None:
            return

        # A poll that started before the command still reports the previous
        # value, so the value of the command is kept until the matrix reports it.
        self._pending.record(section, port, value)

        self._async_publish(
            {**self.data, section: {**self.data[section], port: value}},
            context,
        )

    @callback
    def _async_revert(
        self,
        section: _Section,
        port: int,
        previous: int | bool | None,
        context: Context | None,
    ) -> None:
        """Restore the value a port had before a command that failed.

        Whether the matrix applied the command is unknown, because a command
        that timed out may still have reached it. No value is kept against the
        next poll, which shows the actual state. The routing is read on every
        poll anyway, while the settings are read right away instead of after
        the regular interval.
        """
        if self.data is None:
            return

        self._pending.discard(section, port)

        if section != "outputs":
            self._settings_stale = True

        values = dict(self.data[section])

        if previous is None:
            values.pop(port, None)
        else:
            values[port] = previous

        self._async_publish({**self.data, section: values}, context)

    @callback
    def _async_publish(self, data: AVAccessStatus, context: Context | None) -> None:
        """Publish a state that belongs to a command of the user.

        The state is handed to the entities directly instead of through
        async_set_updated_data, which would also mark the matrix as reachable
        and restart the polling interval. Neither is true for a value that has
        not been sent yet or for a command that just failed.
        """
        self._command_update = True
        self._command_context = context

        try:
            self.data = data
            self.async_update_listeners()

        finally:
            self._command_update = False
            self._command_context = None

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
        """Read the routing, and the settings of every port once they are due.

        Somebody switches the routing at the front panel or with the remote
        control, so it is read on every poll with a single command. EDID, HDCP,
        audio mute and the CEC settings are hardly ever changed at the matrix
        and cost twenty commands, so they are only read every
        SETTINGS_POLL_INTERVAL seconds. Commands from Home Assistant need no
        poll at all, as the matrix confirms them right away.

        The first poll reads everything and also finds out which command
        groups the matrix supports, which later polls must not change.
        """
        started = self.hass.loop.time()

        if self.data is None:
            status = await self.client.async_get_status()
            self._settings_read_at = started

            return status

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

        if self._settings_due(started):
            # A command that fails while the settings are read asks for them
            # again, which must survive the end of this read.
            self._settings_stale = False

            try:
                await self._async_read_input_states(edid, hdcp, read)
                await self._async_read_output_states(
                    audio_mute, cec_auto, cec_delay, read
                )

            except BaseException:
                self._settings_stale = True
                raise

            self._settings_read_at = started

        status: AVAccessStatus = {
            "outputs": outputs,
            "edid": edid,
            "hdcp": hdcp,
            "audio_mute": audio_mute,
            "cec_auto": cec_auto,
            "cec_delay": cec_delay,
        }

        # Reading the whole state takes a moment, in which a command can change
        # it. The values are therefore compared with the pending ones
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

    def _settings_due(self, now: float) -> bool:
        """Return whether this poll has to read the settings of the ports."""
        return (
            self._settings_stale
            or self._settings_read_at is None
            or now - self._settings_read_at >= SETTINGS_POLL_INTERVAL
        )

    async def _async_read_input_states(
        self,
        edid: dict[int, int],
        hdcp: dict[int, bool],
        read: list[tuple[_Section, int]],
    ) -> None:
        """Read the EDID and the HDCP state of every input into the values.

        Only ports the matrix reported during the setup have entities, so no
        other port is queried and no entity appears afterwards. A value the
        matrix does not report this time keeps the previous one.
        """
        for input_number in range(1, self.device_info.input_count + 1):
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
        """Read the audio mute and the CEC settings of every output.

        Like the inputs, only ports the matrix reported during the setup are
        queried, and a value the matrix does not report keeps the previous one.
        """
        for output in range(1, self.device_info.output_count + 1):
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
