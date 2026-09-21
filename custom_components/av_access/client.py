"""Client for the Telnet protocol of an AV Access HDMI matrix.

The matrix exposes a line based protocol on its Telnet port. Every command is
answered on the same connection, which the matrix closes afterwards, so one
connection per command is used. The matrix reacts badly to commands that arrive
back to back, therefore all communication passes through a single lock, and a
command may only start once the pause the previous one earned has elapsed.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import re
from typing import NamedTuple, TypedDict

from .const import (
    CLOSE_TIMEOUT,
    COMMAND_DELAY,
    CONNECT_TIMEOUT,
    DEFAULT_INPUT_COUNT,
    DEFAULT_OUTPUT_COUNT,
    IDLE_TIMEOUT,
    MANUFACTURER,
    READ_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

COMMAND_VERSION = "GET VER"
COMMAND_IP_ADDRESS = "GET IPADDR"
COMMAND_IP_MODE = "GET IP MODE"
COMMAND_ROUTING_ALL = "GET MP all"
COMMAND_ROUTING = "GET MP hdmiout{output}"
COMMAND_SET_ROUTING = "SET SW hdmiin{input} hdmiout{output}"
COMMAND_EDID = "GET EDID hdmiin{input}"
COMMAND_SET_EDID = "SET EDID hdmiin{input} {edid}"
COMMAND_HDCP = "GET HDCP_S hdmiin{input}"
COMMAND_SET_HDCP = "SET HDCP_S hdmiin{input} {value}"
COMMAND_AUDIO_MUTE = "GET MUTE audioout{output}"
COMMAND_SET_AUDIO_MUTE = "SET MUTE audioout{output} {value}"

# The matrix answers a command it does not know with its welcome line, which is
# also the only place where it reports its model without being asked.
GREETING_PATTERN = re.compile(r"welcome\s+to\s+the\s+(\S+)\s+matrix", re.IGNORECASE)

# Depending on the firmware the routing is reported as "MP hdmiin2 hdmiout1",
# "MP in2 hdmiout1" or the other way round as "MP hdmiout1 in2".
MAPPING_PATTERN = re.compile(
    r"^MP\s+(?:hdmi)?in(\d+)\s+(?:hdmi)?out(\d+)\b",
    re.IGNORECASE,
)
REVERSE_MAPPING_PATTERN = re.compile(
    r"^MP\s+(?:hdmi)?out(\d+)\s+(?:hdmi)?in(\d+)\b",
    re.IGNORECASE,
)

SWITCH_PATTERN = re.compile(
    r"^SW\s+(?:hdmi)?in(\d+)\s+(?:hdmi)?out(\d+)\b",
    re.IGNORECASE,
)
EDID_PATTERN = re.compile(r"^EDID\s+hdmiin(\d+)\s+(\d+)\b", re.IGNORECASE)
HDCP_PATTERN = re.compile(
    r"^HDCP_S\s+hdmiin(\d+)\s+(on|off|enabled?|disabled?|1|0)\b",
    re.IGNORECASE,
)
AUDIO_MUTE_PATTERN = re.compile(
    r"^MUTE\s+audioout(\d+)\s+(on|off|enabled?|disabled?|1|0)\b",
    re.IGNORECASE,
)

# "4KMX44-H2 VER 1.0, ARM VER 1.0"
VERSION_PATTERN = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9._-]*)\s+VER\s+(V?\d[\w.-]*)",
    re.IGNORECASE,
)

# "IPADDR IP:192.168.1.4 MASK:255.255.255.0 GATE:192.168.1.1"
IP_FIELD_PATTERN = re.compile(
    r"\b(IP|MASK|GATE)\s*:\s*(\d{1,3}(?:\.\d{1,3}){3})",
    re.IGNORECASE,
)
IP_MODE_PATTERN = re.compile(r"^IP\s+MODE\s+([A-Za-z]+)\b", re.IGNORECASE)

# The model name carries the port layout, for example 4KMX44-H2 is a 4x4 matrix.
MODEL_PORTS_PATTERN = re.compile(r"MX(\d+)", re.IGNORECASE)

ID_SANITIZE_PATTERN = re.compile(r"[^a-z0-9]+")

# Labels of GET VER that name a firmware instead of the model.
FIRMWARE_LABELS = frozenset({"MCU", "MASTER", "FW", "FIRMWARE"})

HDCP_ON_VALUES = frozenset({"on", "enable", "enabled", "1"})
AUDIO_MUTE_ON_VALUES = frozenset({"on", "enable", "enabled", "1"})


class AVAccessStatus(TypedDict):
    """Current state of the matrix, keyed by port number."""

    outputs: dict[int, int]
    edid: dict[int, int]
    hdcp: dict[int, bool]
    audio_mute: dict[int, bool]


class AVAccessError(Exception):
    """Base exception for all matrix errors."""


class AVAccessConnectionError(AVAccessError):
    """Exception raised when the matrix cannot be reached."""


class AVAccessTimeoutError(AVAccessConnectionError):
    """Exception raised when the matrix does not answer in time."""


class AVAccessProtocolError(AVAccessError):
    """Exception raised when the matrix returns an unexpected response."""


class VersionInfo(NamedTuple):
    """Model and firmware versions reported by ``GET VER``."""

    model: str | None = None
    sw_version: str | None = None
    arm_version: str | None = None


class NetworkInfo(NamedTuple):
    """Network settings reported by ``GET IPADDR``."""

    ip_address: str | None = None
    netmask: str | None = None
    gateway: str | None = None


@dataclass(frozen=True, kw_only=True)
class AVAccessDeviceInfo:
    """Static information the matrix reports about itself."""

    unique_id: str
    model: str | None = None
    manufacturer: str | None = None
    sw_version: str | None = None
    hw_version: str | None = None
    arm_version: str | None = None
    configuration_url: str | None = None
    ip_address: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    ip_mode: str | None = None
    input_count: int = DEFAULT_INPUT_COUNT
    output_count: int = DEFAULT_OUTPUT_COUNT
    updated_at: datetime | None = None


def response_lines(response: str) -> list[str]:
    """Return the non-empty lines of a response.

    The matrix separates the lines of ``GET MP all`` with a single carriage
    return and only terminates the last one with CRLF.
    """
    return [line.strip() for line in response.splitlines() if line.strip()]


def parse_greeting_model(response: str) -> str | None:
    """Return the model from a welcome line, if the response carries one."""
    for line in response_lines(response):
        if match := GREETING_PATTERN.search(line):
            return match.group(1).strip("!.,")

    return None


def parse_routing_response(
    response: str,
    input_count: int,
    output_count: int,
) -> dict[int, int]:
    """Return the input routed to every output reported by the response."""
    routing: dict[int, int] = {}

    for line in response_lines(response):
        if match := MAPPING_PATTERN.match(line):
            input_number, output = int(match.group(1)), int(match.group(2))

        elif match := REVERSE_MAPPING_PATTERN.match(line):
            output, input_number = int(match.group(1)), int(match.group(2))

        else:
            continue

        # A line reporting a port the matrix does not have is not trustworthy.
        if 1 <= input_number <= input_count and 1 <= output <= output_count:
            routing[output] = input_number

    return routing


def parse_switch_response(response: str, output: int) -> int | None:
    """Return the input the matrix confirmed for an output."""
    for line in response_lines(response):
        if (match := SWITCH_PATTERN.match(line)) and int(match.group(2)) == output:
            return int(match.group(1))

    return None


def parse_edid_response(response: str, input_number: int) -> int | None:
    """Return the EDID the matrix reports for an input."""
    for line in response_lines(response):
        if (match := EDID_PATTERN.match(line)) and int(match.group(1)) == input_number:
            return int(match.group(2))

    return None


def parse_hdcp_response(response: str, input_number: int) -> bool | None:
    """Return the HDCP state the matrix reports for an input."""
    for line in response_lines(response):
        if (match := HDCP_PATTERN.match(line)) and int(match.group(1)) == input_number:
            return match.group(2).lower() in HDCP_ON_VALUES

    return None


def parse_audio_mute_response(response: str, output: int) -> bool | None:
    """Return whether audio is muted for an output."""
    for line in response_lines(response):
        if (match := AUDIO_MUTE_PATTERN.match(line)) and int(match.group(1)) == output:
            return match.group(2).lower() in AUDIO_MUTE_ON_VALUES

    return None


def parse_version_response(response: str) -> VersionInfo:
    """Return the model and the firmware versions from a ``GET VER`` response."""
    model: str | None = None
    sw_version: str | None = None
    arm_version: str | None = None

    for line in response_lines(response):
        for label, version in VERSION_PATTERN.findall(line):
            if label.upper() == "ARM":
                arm_version = arm_version or version

            elif label.upper() in FIRMWARE_LABELS:
                sw_version = sw_version or version

            else:
                # Anything else is the model, which reports its own firmware.
                model = model or label
                sw_version = sw_version or version

    return VersionInfo(model, sw_version, arm_version)


def parse_network_response(response: str) -> NetworkInfo:
    """Return the network settings from a ``GET IPADDR`` response."""
    fields: dict[str, str] = {}

    for line in response_lines(response):
        for field, value in IP_FIELD_PATTERN.findall(line):
            fields.setdefault(field.upper(), value)

    return NetworkInfo(
        ip_address=fields.get("IP"),
        netmask=fields.get("MASK"),
        gateway=fields.get("GATE"),
    )


def parse_ip_mode_response(response: str) -> str | None:
    """Return the addressing mode from a ``GET IP MODE`` response."""
    for line in response_lines(response):
        if match := IP_MODE_PATTERN.match(line):
            return match.group(1).lower()

    return None


def ports_from_model(model: str | None) -> tuple[int, int] | None:
    """Return the number of inputs and outputs a model name describes."""
    if not model:
        return None

    match = MODEL_PORTS_PATTERN.search(model)

    if match is None:
        return None

    # The digits hold the inputs followed by the outputs, for example MX44.
    digits = match.group(1)

    if len(digits) % 2:
        return None

    half = len(digits) // 2
    inputs, outputs = int(digits[:half]), int(digits[half:])

    if inputs < 1 or outputs < 1:
        return None

    return inputs, outputs


def build_unique_id(model: str | None, host: str) -> str:
    """Return an ID that stays the same as long as the matrix keeps its address.

    The command set of the matrix reports neither a serial number nor a MAC
    address, so the model and the configured address are the only stable parts.
    """
    base = f"{model}-{host}" if model else host

    return ID_SANITIZE_PATTERN.sub("-", base.lower()).strip("-")


class AVAccessClient:
    """Talk to an AV Access HDMI matrix over TCP."""

    def __init__(self, host: str, port: int) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port

        # Exactly one command may be in flight per matrix, so this lock guards
        # every single command, no matter which caller sends it.
        self._command_lock = asyncio.Lock()

        # Loop time before which the matrix must not receive the next command.
        self._next_command_at = 0.0

        self._input_count = DEFAULT_INPUT_COUNT
        self._output_count = DEFAULT_OUTPUT_COUNT

        self._bulk_routing_supported = True
        self._hdcp_supported = True

    @property
    def host(self) -> str:
        """Return the address of the matrix."""
        return self._host

    @property
    def input_count(self) -> int:
        """Return the number of inputs of the matrix."""
        return self._input_count

    @property
    def hdcp_supported(self) -> bool:
        """Return whether the matrix understands the HDCP commands."""
        return self._hdcp_supported

    async def async_send_command(self, command: str) -> str:
        """Send a command to the matrix and return its raw response.

        This is the only place that performs I/O with the matrix.
        """
        async with self._command_lock:
            loop = asyncio.get_running_loop()

            # The pause is waited out before the command instead of after it,
            # but still under the lock. The matrix sees the same spacing, while
            # a caller that arrives once the matrix has rested waits for nothing.
            if (pause := self._next_command_at - loop.time()) > 0:
                await asyncio.sleep(pause)

            try:
                return await self._async_execute_command(command)

            finally:
                # A failed attempt earns the pause as well, otherwise a broken
                # connection would result in a burst of commands.
                self._next_command_at = loop.time() + COMMAND_DELAY

    async def async_get_device_info(self) -> AVAccessDeviceInfo:
        """Read the static information the matrix reports about itself."""
        version_response = await self.async_send_command(COMMAND_VERSION)
        version = parse_version_response(version_response)

        # A matrix that does not know GET VER answers with its welcome line,
        # which still names the model.
        model = version.model or parse_greeting_model(version_response)

        network = parse_network_response(
            await self.async_send_command(COMMAND_IP_ADDRESS)
        )
        ip_mode = parse_ip_mode_response(await self.async_send_command(COMMAND_IP_MODE))

        if ports := ports_from_model(model):
            self._input_count, self._output_count = ports

        ip_address = network.ip_address or self._host

        return AVAccessDeviceInfo(
            unique_id=build_unique_id(model, self._host),
            model=model,
            manufacturer=MANUFACTURER,
            sw_version=version.sw_version,
            # The command set does not report a hardware revision.
            hw_version=None,
            arm_version=version.arm_version,
            configuration_url=f"http://{ip_address}",
            ip_address=network.ip_address,
            netmask=network.netmask,
            gateway=network.gateway,
            ip_mode=ip_mode,
            input_count=self._input_count,
            output_count=self._output_count,
            updated_at=datetime.now(UTC),
        )

    async def async_get_status(self) -> AVAccessStatus:
        """Return the complete state of the matrix.

        The commands are sent one after another on purpose. Running them
        concurrently would queue them behind the command lock anyway and must
        never be attempted.
        """
        outputs = await self.async_get_routing()
        edid = await self.async_get_edid()
        hdcp = await self.async_get_hdcp()
        audio_mute = await self.async_get_audio_mute()

        return {
            "outputs": outputs,
            "edid": edid,
            "hdcp": hdcp,
            "audio_mute": audio_mute,
        }

    async def async_get_routing(self) -> dict[int, int]:
        """Return the input that is routed to every output."""
        if self._bulk_routing_supported:
            routing = parse_routing_response(
                await self.async_send_command(COMMAND_ROUTING_ALL),
                input_count=self._input_count,
                output_count=self._output_count,
            )

            if routing:
                return routing

            # An unsupported command is answered with the welcome line, so this
            # matrix needs one command per output from now on.
            self._bulk_routing_supported = False

            _LOGGER.debug(
                "The matrix does not support %s, querying every output",
                COMMAND_ROUTING_ALL,
            )

        routing: dict[int, int] = {}

        for output in range(1, self._output_count + 1):
            routing.update(
                parse_routing_response(
                    await self.async_send_command(
                        COMMAND_ROUTING.format(output=output)
                    ),
                    input_count=self._input_count,
                    output_count=self._output_count,
                )
            )

        if not routing:
            raise AVAccessProtocolError("The matrix did not report its routing")

        return routing

    async def async_get_edid(self) -> dict[int, int]:
        """Return the EDID of every input."""
        edid: dict[int, int] = {}

        for input_number in range(1, self._input_count + 1):
            value = await self.async_get_input_edid(input_number)

            if value is not None:
                edid[input_number] = value

        return edid

    async def async_get_input_edid(self, input_number: int) -> int | None:
        """Return the EDID of a single input."""
        return parse_edid_response(
            await self.async_send_command(COMMAND_EDID.format(input=input_number)),
            input_number,
        )

    async def async_get_hdcp(self) -> dict[int, bool]:
        """Return the HDCP state of every input.

        A matrix without HDCP commands reports no state at all, which keeps the
        HDCP entities from being created.
        """
        if not self._hdcp_supported:
            return {}

        hdcp: dict[int, bool] = {}

        for input_number in range(1, self._input_count + 1):
            value = await self.async_get_input_hdcp(input_number)

            if value is None:
                # Unknown commands are answered with the welcome line, so a
                # matrix without HDCP support is recognized on the first input.
                if not hdcp:
                    self._hdcp_supported = False

                    _LOGGER.debug("The matrix does not support HDCP commands")

                    return {}

                continue

            hdcp[input_number] = value

        return hdcp

    async def async_get_input_hdcp(self, input_number: int) -> bool | None:
        """Return the HDCP state of a single input."""
        if not self._hdcp_supported:
            return None

        return parse_hdcp_response(
            await self.async_send_command(COMMAND_HDCP.format(input=input_number)),
            input_number,
        )

    async def async_set_output(self, output: int, input_number: int) -> int:
        """Route an HDMI input to an output and return the confirmed input."""
        response = await self.async_send_command(
            COMMAND_SET_ROUTING.format(input=input_number, output=output)
        )

        confirmed = parse_switch_response(response, output)

        if confirmed is None:
            raise AVAccessProtocolError(
                f"The matrix did not confirm routing input {input_number} to "
                f"output {output}: {response!r}"
            )

        return confirmed

    async def async_set_edid(self, input_number: int, edid: int) -> int:
        """Set the EDID of an HDMI input and return the confirmed EDID."""
        response = await self.async_send_command(
            COMMAND_SET_EDID.format(input=input_number, edid=edid)
        )

        confirmed = parse_edid_response(response, input_number)

        if confirmed is None:
            raise AVAccessProtocolError(
                f"The matrix did not confirm EDID {edid} for input "
                f"{input_number}: {response!r}"
            )

        return confirmed

    async def async_set_hdcp(self, input_number: int, enabled: bool) -> bool:
        """Switch HDCP support of an HDMI input and return the confirmed state."""
        response = await self.async_send_command(
            COMMAND_SET_HDCP.format(
                input=input_number,
                value="on" if enabled else "off",
            )
        )

        confirmed = parse_hdcp_response(response, input_number)

        if confirmed is None:
            raise AVAccessProtocolError(
                f"The matrix did not confirm the HDCP state of input "
                f"{input_number}: {response!r}"
            )

        return confirmed

    async def async_get_audio_mute(self) -> dict[int, bool]:
        """Return the mute state of every audio output."""
        audio_mute: dict[int, bool] = {}

        for output in range(1, self._output_count + 1):
            value = await self.async_get_output_audio_mute(output)

            if value is not None:
                audio_mute[output] = value

        return audio_mute

    async def async_get_output_audio_mute(self, output: int) -> bool | None:
        """Return whether audio is muted for an output."""
        return parse_audio_mute_response(
            await self.async_send_command(COMMAND_AUDIO_MUTE.format(output=output)),
            output,
        )

    async def async_set_audio_mute(self, output: int, muted: bool) -> bool:
        """Set the audio mute state of an output and return the confirmed state."""
        response = await self.async_send_command(
            COMMAND_SET_AUDIO_MUTE.format(
                output=output,
                value="on" if muted else "off",
            )
        )

        confirmed = parse_audio_mute_response(response, output)

        if confirmed is None:
            raise AVAccessProtocolError(
                f"The matrix did not confirm the audio mute state of output "
                f"{output}: {response!r}"
            )

        return confirmed

    async def _async_execute_command(self, command: str) -> str:
        """Open a connection, send one command and read the whole response."""
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                reader, writer = await asyncio.open_connection(self._host, self._port)

        except TimeoutError as err:
            raise AVAccessTimeoutError(
                f"Connecting to the AV Access matrix at {self._host}:{self._port} "
                f"timed out"
            ) from err

        except OSError as err:
            raise AVAccessConnectionError(
                f"Unable to connect to the AV Access matrix at "
                f"{self._host}:{self._port}: {err}"
            ) from err

        try:
            writer.write(f"{command}\r\n".encode())

            async with asyncio.timeout(READ_TIMEOUT):
                await writer.drain()

                # The matrix answers until it closes the connection, so the
                # write side is closed to signal that nothing else follows.
                if writer.can_write_eof():
                    writer.write_eof()

                # A closing matrix ends the read with EOF right away. A firmware
                # that keeps the connection open sends the answer in one burst,
                # so a short pause after the received data marks its end instead
                # of running into READ_TIMEOUT.
                chunks: list[bytes] = []

                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            reader.read(4096),
                            timeout=IDLE_TIMEOUT,
                        )

                    except TimeoutError:
                        if chunks:
                            break

                        continue

                    if not chunk:
                        break

                    chunks.append(chunk)

                raw = b"".join(chunks)

        except TimeoutError as err:
            raise AVAccessTimeoutError(
                f"The AV Access matrix at {self._host}:{self._port} did not "
                f"answer {command!r} in time"
            ) from err

        except OSError as err:
            raise AVAccessConnectionError(
                f"Communication with the AV Access matrix at "
                f"{self._host}:{self._port} failed: {err}"
            ) from err

        finally:
            writer.close()

            # A matrix that keeps the connection open must not block the lock.
            with suppress(OSError, TimeoutError):
                async with asyncio.timeout(CLOSE_TIMEOUT):
                    await writer.wait_closed()

        response = raw.decode("utf-8", "replace").strip()

        if not response:
            raise AVAccessProtocolError(
                f"The AV Access matrix at {self._host}:{self._port} did not "
                f"answer {command!r}"
            )

        _LOGGER.debug("Command %r returned %r", command, response)

        return response
