"""Telnet emulator of an AV Access 4KMX44-H2 HDMI matrix.

The emulator speaks the line based protocol of the "API Command Set
4KMX44-H2 V1.0.0" document and reproduces the behaviour the client of the
integration relies on:

* every command is answered on the connection it arrived on, and the matrix
  closes that connection afterwards,
* a command the matrix does not know is answered with its welcome line, which
  is the only place the model is reported without being asked,
* the lines of a multi line answer are separated by a single carriage return
  and only the last one ends with CRLF.

Everything the emulated matrix reports can be changed through environment
variables, so the integration can be exercised against a matrix without HDCP
or CEC support, against a firmware that keeps connections open and against a
matrix whose state changes without a command, as it does when somebody
switches at the front panel.

The module only uses the standard library so the container needs no
dependencies.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import random
import re

_LOGGER = logging.getLogger("av_access_emulator")

# Answer of the matrix to a command it does not know. It names the model, which
# is how the client recognizes a device without GET VER.
GREETING = "Welcome to the {model} matrix!"

# The model name carries the port layout, for example 4KMX44-H2 is a 4x4 matrix.
MODEL_PORTS_PATTERN = re.compile(r"MX(\d+)", re.IGNORECASE)

IP_PATTERN = r"\d{1,3}(?:\.\d{1,3}){3}"

# Telnet escapes an interpreted command with this byte.
IAC = 255
# Commands that are followed by a single option byte.
IAC_OPTION_COMMANDS = frozenset({251, 252, 253, 254})  # WILL, WONT, DO, DONT
IAC_SB = 250
IAC_SE = 240
IAC_WILL = 251
IAC_WONT = 252
IAC_DO = 253
IAC_DONT = 254

# The EDID values the matrix accepts, as reported by its web interface. The
# command set of the first firmware only documents 1 to 13.
EDID_NAMES: dict[int, str] = {
    1: "Copy from output 1",
    2: "Copy from output 2",
    3: "Copy from output 3",
    4: "Copy from output 4",
    5: "4K@60Hz 5.1ch audio With HDR",
    6: "4K@60Hz 2.0ch audio With HDR",
    7: "4K@30Hz 7.1ch audio With HDR",
    8: "4K@30Hz 5.1ch audio With HDR",
    9: "4K@30Hz 2.0ch audio With HDR",
    10: "4K@30Hz/8bit only 2.0ch audio Without HDR",
    11: "1080P@60Hz 2.0ch audio",
    12: "5K Ultra Wide_2CH",
    13: "5K Super Wide_2CH",
    14: "Smart EDID",
    15: "EDID Write",
}

# Defaults of the matrix as documented by the command set.
DEFAULT_EDID = 5
DEFAULT_HDCP = True
DEFAULT_MUTE = False
DEFAULT_CEC_AUTO = True
DEFAULT_CEC_DELAY = 2
DEFAULT_SCALER = True

CEC_DELAY_MIN = 1
CEC_DELAY_MAX = 30

PRESET_NUMBERS = (1, 2, 3)


def _env_str(name: str, default: str) -> str:
    """Return a string setting from the environment."""
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    """Return a boolean setting from the environment."""
    value = os.environ.get(name)

    if value is None or not value.strip():
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """Return an integer setting from the environment."""
    try:
        return int(_env_str(name, str(default)))

    except ValueError:
        _LOGGER.warning("%s is not a number, falling back to %s", name, default)

        return default


def _env_float(name: str, default: float) -> float:
    """Return a float setting from the environment."""
    try:
        return float(_env_str(name, str(default)))

    except ValueError:
        _LOGGER.warning("%s is not a number, falling back to %s", name, default)

        return default


def ports_from_model(model: str) -> tuple[int, int] | None:
    """Return the number of inputs and outputs a model name describes."""
    match = MODEL_PORTS_PATTERN.search(model)

    if match is None:
        return None

    digits = match.group(1)

    if len(digits) % 2:
        return None

    half = len(digits) // 2
    inputs, outputs = int(digits[:half]), int(digits[half:])

    if inputs < 1 or outputs < 1:
        return None

    return inputs, outputs


@dataclass(kw_only=True)
class Config:
    """Settings of the emulated matrix."""

    host: str = "0.0.0.0"
    port: int = 23
    model: str = "4KMX44-H2"
    sw_version: str = "1.0"
    arm_version: str = "1.0"
    input_count: int = 4
    output_count: int = 4
    ip_address: str = "192.168.1.4"
    netmask: str = "255.255.255.0"
    gateway: str = "192.168.1.1"
    ip_mode: str = "dhcp"

    # The real matrix closes the connection once it has answered. A firmware
    # that keeps it open is emulated with false.
    close_after_response: bool = True
    # Some firmwares greet a client as soon as it connects.
    greeting_on_connect: bool = False
    # Seconds the matrix takes before it answers.
    response_delay: float = 0.0
    # Seconds a connection may stay idle before the matrix drops it.
    idle_timeout: float = 300.0

    # A matrix without these commands answers them with its welcome line.
    hdcp_supported: bool = True
    cec_supported: bool = True
    scaler_supported: bool = True
    bulk_routing_supported: bool = True

    # The command set documents "AUTOCEC_FN hdmiout1 on" as the answer of
    # GET AUTOCEC_FN, while its own example shows "AUTOCEC_FN on".
    cec_auto_short_reply: bool = False

    # Seconds between two commands below which the matrix is overloaded. The
    # real device has been observed to freeze when commands arrive back to back.
    min_command_gap: float = 0.0
    # Seconds the matrix stops answering after it was overloaded.
    freeze_duration: float = 0.0

    # Seconds between two state changes the emulator performs on its own, which
    # is what a switch at the front panel looks like. Zero turns this off.
    drift_interval: float = 0.0
    drift_seed: int | None = None

    # File the state is written to, so it survives a restart. Empty disables it.
    state_file: str = ""

    @classmethod
    def from_env(cls) -> Config:
        """Return the configuration described by the environment."""
        model = _env_str("AVA_MODEL", "4KMX44-H2")
        ports = ports_from_model(model) or (4, 4)
        seed = _env_str("AVA_DRIFT_SEED", "")

        return cls(
            host=_env_str("AVA_HOST", "0.0.0.0"),
            port=_env_int("AVA_PORT", 23),
            model=model,
            sw_version=_env_str("AVA_SW_VERSION", "1.0"),
            arm_version=_env_str("AVA_ARM_VERSION", "1.0"),
            input_count=_env_int("AVA_INPUT_COUNT", ports[0]),
            output_count=_env_int("AVA_OUTPUT_COUNT", ports[1]),
            ip_address=_env_str("AVA_IP_ADDRESS", "192.168.1.4"),
            netmask=_env_str("AVA_NETMASK", "255.255.255.0"),
            gateway=_env_str("AVA_GATEWAY", "192.168.1.1"),
            ip_mode=_env_str("AVA_IP_MODE", "dhcp").lower(),
            close_after_response=_env_bool("AVA_CLOSE_AFTER_RESPONSE", True),
            greeting_on_connect=_env_bool("AVA_GREETING_ON_CONNECT", False),
            response_delay=_env_float("AVA_RESPONSE_DELAY", 0.0),
            idle_timeout=_env_float("AVA_IDLE_TIMEOUT", 300.0),
            hdcp_supported=_env_bool("AVA_HDCP_SUPPORTED", True),
            cec_supported=_env_bool("AVA_CEC_SUPPORTED", True),
            scaler_supported=_env_bool("AVA_SCALER_SUPPORTED", True),
            bulk_routing_supported=_env_bool("AVA_BULK_ROUTING_SUPPORTED", True),
            cec_auto_short_reply=_env_bool("AVA_CEC_AUTO_SHORT_REPLY", False),
            min_command_gap=_env_float("AVA_MIN_COMMAND_GAP", 0.0),
            freeze_duration=_env_float("AVA_FREEZE_DURATION", 0.0),
            drift_interval=_env_float("AVA_DRIFT_INTERVAL", 0.0),
            drift_seed=int(seed) if seed else None,
            state_file=_env_str("AVA_STATE_FILE", ""),
        )


@dataclass
class MatrixState:
    """Everything the emulated matrix remembers, keyed by port number."""

    routing: dict[int, int] = field(default_factory=dict)
    edid: dict[int, int] = field(default_factory=dict)
    hdcp: dict[int, bool] = field(default_factory=dict)
    mute: dict[int, bool] = field(default_factory=dict)
    cec_auto: dict[int, bool] = field(default_factory=dict)
    cec_delay: dict[int, int] = field(default_factory=dict)
    scaler: dict[int, bool] = field(default_factory=dict)
    cec_power: dict[int, bool] = field(default_factory=dict)
    presets: dict[int, dict[int, int]] = field(default_factory=dict)
    ip_address: str = "192.168.1.4"
    netmask: str = "255.255.255.0"
    gateway: str = "192.168.1.1"
    ip_mode: str = "dhcp"

    @classmethod
    def factory(cls, config: Config) -> MatrixState:
        """Return the state the matrix has after a factory reset."""
        inputs = range(1, config.input_count + 1)
        outputs = range(1, config.output_count + 1)

        return cls(
            # The factory default routes every input to the output of the same
            # number, as documented for the preset scenes.
            routing={output: min(output, config.input_count) for output in outputs},
            edid=dict.fromkeys(inputs, DEFAULT_EDID),
            hdcp=dict.fromkeys(inputs, DEFAULT_HDCP),
            mute=dict.fromkeys(outputs, DEFAULT_MUTE),
            cec_auto=dict.fromkeys(outputs, DEFAULT_CEC_AUTO),
            cec_delay=dict.fromkeys(outputs, DEFAULT_CEC_DELAY),
            scaler=dict.fromkeys(outputs, DEFAULT_SCALER),
            cec_power=dict.fromkeys(outputs, True),
            presets={
                preset: {output: min(output, config.input_count) for output in outputs}
                for preset in PRESET_NUMBERS
            },
            ip_address=config.ip_address,
            netmask=config.netmask,
            gateway=config.gateway,
            ip_mode=config.ip_mode,
        )

    def as_dict(self) -> dict:
        """Return the state as JSON compatible data."""
        return {
            "routing": self.routing,
            "edid": self.edid,
            "hdcp": self.hdcp,
            "mute": self.mute,
            "cec_auto": self.cec_auto,
            "cec_delay": self.cec_delay,
            "scaler": self.scaler,
            "cec_power": self.cec_power,
            "presets": self.presets,
            "ip_address": self.ip_address,
            "netmask": self.netmask,
            "gateway": self.gateway,
            "ip_mode": self.ip_mode,
        }

    def update_from_dict(self, data: dict) -> None:
        """Apply stored data, keeping the ports the configuration allows."""
        for name in ("routing", "edid", "cec_delay"):
            stored = data.get(name)

            if isinstance(stored, dict):
                current: dict[int, int] = getattr(self, name)
                current.update(
                    {
                        int(key): int(value)
                        for key, value in stored.items()
                        if int(key) in current
                    }
                )

        for name in ("hdcp", "mute", "cec_auto", "scaler", "cec_power"):
            stored = data.get(name)

            if isinstance(stored, dict):
                current_flags: dict[int, bool] = getattr(self, name)
                current_flags.update(
                    {
                        int(key): bool(value)
                        for key, value in stored.items()
                        if int(key) in current_flags
                    }
                )

        presets = data.get("presets")

        if isinstance(presets, dict):
            for preset, mapping in presets.items():
                if int(preset) in self.presets and isinstance(mapping, dict):
                    self.presets[int(preset)].update(
                        {
                            int(output): int(value)
                            for output, value in mapping.items()
                            if int(output) in self.presets[int(preset)]
                        }
                    )

        for name in ("ip_address", "netmask", "gateway", "ip_mode"):
            value = data.get(name)

            if isinstance(value, str) and value:
                setattr(self, name, value)


def strip_telnet(data: bytes) -> tuple[bytes, bytes]:
    """Return the payload of a line and the answer its Telnet options need.

    An interactive ``telnet`` client starts with option negotiation, which is
    removed from the data the commands are parsed from. Every option is
    refused, which leaves the client in the line mode the matrix expects.
    """
    payload = bytearray()
    reply = bytearray()
    index = 0

    while index < len(data):
        byte = data[index]

        if byte != IAC:
            payload.append(byte)
            index += 1

            continue

        if index + 1 >= len(data):
            break

        command = data[index + 1]

        if command == IAC:
            payload.append(IAC)
            index += 2

        elif command in IAC_OPTION_COMMANDS:
            if index + 2 >= len(data):
                break

            option = data[index + 2]

            # Every option is refused, so the client keeps sending plain lines.
            if command in (IAC_WILL, IAC_WONT):
                reply.extend((IAC, IAC_DONT, option))

            elif command in (IAC_DO, IAC_DONT):
                reply.extend((IAC, IAC_WONT, option))

            index += 3

        elif command == IAC_SB:
            end = data.find(bytes((IAC, IAC_SE)), index)
            index = len(data) if end == -1 else end + 2

        else:
            index += 2

    return bytes(payload), bytes(reply)


class Matrix:
    """The emulated matrix and the commands it understands."""

    def __init__(self, config: Config) -> None:
        """Initialize the matrix with the state of a factory reset."""
        self._config = config
        self._state = MatrixState.factory(config)
        self._state_path = Path(config.state_file) if config.state_file else None
        self._random = random.Random(config.drift_seed)

        # Loop time of the last command, used to notice a burst of commands.
        self._last_command_at: float | None = None
        # Loop time until which the matrix is frozen after such a burst.
        self._frozen_until = 0.0

        self._handlers: list[
            tuple[re.Pattern[str], Callable[[re.Match[str]], list[str] | None]]
        ] = self._build_handlers()

        self._load_state()

    @property
    def config(self) -> Config:
        """Return the configuration of the matrix."""
        return self._config

    @property
    def greeting(self) -> str:
        """Return the welcome line of the matrix."""
        return GREETING.format(model=self._config.model)

    def handle_command(self, command: str) -> list[str]:
        """Return the lines the matrix answers a command with."""
        for pattern, handler in self._handlers:
            match = pattern.fullmatch(command)

            if match is None:
                continue

            response = handler(match)

            # A handler that refuses a command leaves it to the welcome line,
            # which is how the matrix answers anything it cannot carry out.
            if response is not None:
                self._save_state()

                return response

            break

        return [self.greeting]

    def note_command(self, now: float) -> bool:
        """Return whether the matrix answers, remembering when it was asked.

        Commands that arrive faster than the configured gap overload the real
        matrix, which then stops answering for a while.
        """
        previous, self._last_command_at = self._last_command_at, now

        if now < self._frozen_until:
            return False

        gap = self._config.min_command_gap

        if gap <= 0 or previous is None or now - previous >= gap:
            return True

        _LOGGER.warning(
            "Commands arrived %.3f s apart, which is faster than the %.3f s "
            "the matrix needs",
            now - previous,
            gap,
        )

        if self._config.freeze_duration > 0:
            self._frozen_until = now + self._config.freeze_duration

            _LOGGER.warning(
                "The matrix stops answering for %.1f s",
                self._config.freeze_duration,
            )

            return False

        return True

    def drift(self) -> str | None:
        """Change one setting the way somebody at the front panel would."""
        changes = (
            self._drift_routing,
            self._drift_mute,
            self._drift_edid,
            self._drift_hdcp,
            self._drift_cec_auto,
            self._drift_cec_delay,
        )
        description = self._random.choice(changes)()

        if description is not None:
            self._save_state()

        return description

    def _build_handlers(
        self,
    ) -> list[tuple[re.Pattern[str], Callable[[re.Match[str]], list[str] | None]]]:
        """Return the commands of the matrix and the code that carries them out."""
        definitions: list[tuple[str, Callable[[re.Match[str]], list[str] | None]]] = [
            (r"help", self._help),
            (r"GET\s+VER", self._get_version),
            (r"GET\s+IPADDR", self._get_ip_address),
            (
                rf"SET\s+IPADDR\s+({IP_PATTERN})\s+({IP_PATTERN})\s+({IP_PATTERN})",
                self._set_ip_address,
            ),
            (r"GET\s+IP\s+MODE", self._get_ip_mode),
            (r"SET\s+IP\s+MODE\s+(static|dhcp)", self._set_ip_mode),
            (r"GET\s+MP\s+all", self._get_routing_all),
            (r"GET\s+MP\s+hdmiout(\d+)", self._get_routing),
            (r"SET\s+SW\s+hdmiin(\d+)\s+hdmiout(\d+)", self._set_routing),
            (r"SET\s+SW\s+hdmiin(\d+)\s+all", self._set_routing_all),
            (r"GET\s+EDID\s+all", self._get_edid_all),
            (r"GET\s+EDID\s+hdmiin(\d+)", self._get_edid),
            (r"SET\s+EDID\s+hdmiin(\d+)\s+(\d+)", self._set_edid),
            (r"GET\s+HDCP_S\s+hdmiin(\d+)", self._get_hdcp),
            (r"SET\s+HDCP_S\s+hdmiin(\d+)\s+(on|off)", self._set_hdcp),
            (r"GET\s+MUTE\s+audioout(\d+)", self._get_mute),
            (r"SET\s+MUTE\s+audioout(\d+)\s+(on|off)", self._set_mute),
            (r"SET\s+MUTE\s+all\s+(on|off)", self._set_mute_all),
            (r"GET\s+AUTOCEC_FN\s+hdmiout(\d+)", self._get_cec_auto),
            (r"SET\s+AUTOCEC_FN\s+hdmiout(\d+)\s+(on|off)", self._set_cec_auto),
            (r"GET\s+AUTOCEC_D\s+hdmiout(\d+)", self._get_cec_delay),
            (r"SET\s+AUTOCEC_D\s+hdmiout(\d+)\s+(\d+)", self._set_cec_delay),
            (r"SET\s+CEC_PWR\s+hdmiout(\d+)\s+(on|off)", self._set_cec_power),
            (r"SET\s+CEC_PWR\s+all\s+(on|off)", self._set_cec_power_all),
            (r"GET\s+SCALER\s+hdmiout(\d+)", self._get_scaler),
            (r"SET\s+SCALER\s+hdmiout(\d+)\s+(on|off)", self._set_scaler),
            (r"SET\s+SCALER\s+all\s+(on|off)", self._set_scaler_all),
            (r"SAVE\s+PRESET\s+(\d+)", self._save_preset),
            (r"RESTORE\s+PRESET\s+(\d+)", self._restore_preset),
            (r"RESET", self._reset),
            (r"REBOOT", self._reboot),
            (r"UPG\s+(MASTER|ARM)", self._upgrade),
        ]

        return [
            (re.compile(pattern, re.IGNORECASE), handler)
            for pattern, handler in definitions
        ]

    def _input(self, value: str) -> int | None:
        """Return the input number of a port token the matrix has."""
        number = int(value)

        return number if 1 <= number <= self._config.input_count else None

    def _output(self, value: str) -> int | None:
        """Return the output number of a port token the matrix has."""
        number = int(value)

        return number if 1 <= number <= self._config.output_count else None

    @property
    def _inputs(self) -> range:
        """Return the input numbers of the matrix."""
        return range(1, self._config.input_count + 1)

    @property
    def _outputs(self) -> range:
        """Return the output numbers of the matrix."""
        return range(1, self._config.output_count + 1)

    def _help(self, _: re.Match[str]) -> list[str]:
        """Return the API list of the matrix.

        The list is meant to be read by a person, so its lines are separated by
        CRLF instead of the carriage return the answers of the commands use.
        """
        lines = [
            "------------------Command Set-----------------",
            "SET SW hdmiin[x] hdmiout[y] : Switch input to output",
            "SET SW hdmiin[x] all        : Switch input to all outputs",
            "GET MP hdmiout[y]           : Get input of output",
            "GET MP all                  : Get input of all outputs",
            "SET EDID hdmiin[x] [1-15]   : Set input EDID",
            "GET EDID hdmiin[x]          : Get input EDID",
            "GET EDID all                : Get EDID of all inputs",
            "SET HDCP_S hdmiin[x] on|off : Set input HDCP support",
            "GET HDCP_S hdmiin[x]        : Get input HDCP support",
            "SET MUTE audioout[y] on|off : Set audio output mute",
            "GET MUTE audioout[y]        : Get audio output mute",
            "SET CEC_PWR hdmiout[y] on|off  : Power sink on or off",
            "SET AUTOCEC_FN hdmiout[y] on|off : Set auto power function",
            "GET AUTOCEC_FN hdmiout[y]   : Get auto power function",
            "SET AUTOCEC_D hdmiout[y] [1-30] : Set auto power delay",
            "GET AUTOCEC_D hdmiout[y]    : Get auto power delay",
            "SET SCALER hdmiout[y] on|off: Set output scaler",
            "GET SCALER hdmiout[y]       : Get output scaler",
            "SAVE PRESET [1-3]           : Save preset scene",
            "RESTORE PRESET [1-3]        : Restore preset scene",
            "SET IPADDR [ip] [mask] [gateway] : Set network settings",
            "GET IPADDR                  : Get network settings",
            "SET IP MODE static|dhcp     : Set addressing mode",
            "GET IP MODE                 : Get addressing mode",
            "GET VER                     : Get firmware versions",
            "UPG MASTER|ARM              : Upgrade module",
            "RESET                       : Factory reset",
            "REBOOT                      : System reboot",
            "----------------------------------------------",
        ]

        return ["\r\n".join(lines)]

    def _get_version(self, _: re.Match[str]) -> list[str]:
        """Return the model and the firmware versions."""
        return [
            f"{self._config.model} VER {self._config.sw_version}, "
            f"ARM VER {self._config.arm_version}"
        ]

    def _get_ip_address(self, _: re.Match[str]) -> list[str]:
        """Return the network settings."""
        return [
            f"IPADDR IP:{self._state.ip_address} MASK:{self._state.netmask} "
            f"GATE:{self._state.gateway}"
        ]

    def _set_ip_address(self, match: re.Match[str]) -> list[str]:
        """Apply network settings."""
        self._state.ip_address = match.group(1)
        self._state.netmask = match.group(2)
        self._state.gateway = match.group(3)
        self._state.ip_mode = "static"

        return self._get_ip_address(match)

    def _get_ip_mode(self, _: re.Match[str]) -> list[str]:
        """Return the addressing mode."""
        return [f"IP MODE {self._state.ip_mode}"]

    def _set_ip_mode(self, match: re.Match[str]) -> list[str]:
        """Apply the addressing mode."""
        self._state.ip_mode = match.group(1).lower()

        return self._get_ip_mode(match)

    def _get_routing_all(self, _: re.Match[str]) -> list[str] | None:
        """Return the input of every output."""
        if not self._config.bulk_routing_supported:
            return None

        return [
            f"MP hdmiin{self._state.routing[output]} hdmiout{output}"
            for output in self._outputs
        ]

    def _get_routing(self, match: re.Match[str]) -> list[str] | None:
        """Return the input of a single output."""
        output = self._output(match.group(1))

        if output is None:
            return None

        return [f"MP hdmiin{self._state.routing[output]} hdmiout{output}"]

    def _set_routing(self, match: re.Match[str]) -> list[str] | None:
        """Route an input to an output."""
        input_number = self._input(match.group(1))
        output = self._output(match.group(2))

        if input_number is None or output is None:
            return None

        self._state.routing[output] = input_number

        return [f"SW hdmiin{input_number} hdmiout{output}"]

    def _set_routing_all(self, match: re.Match[str]) -> list[str] | None:
        """Route an input to every output."""
        input_number = self._input(match.group(1))

        if input_number is None:
            return None

        for output in self._outputs:
            self._state.routing[output] = input_number

        return [f"SW hdmiin{input_number} all"]

    def _get_edid_all(self, _: re.Match[str]) -> list[str]:
        """Return the EDID of every input."""
        return [
            f"EDID hdmiin{number} {self._state.edid[number]:02d}"
            for number in self._inputs
        ]

    def _get_edid(self, match: re.Match[str]) -> list[str] | None:
        """Return the EDID of a single input."""
        input_number = self._input(match.group(1))

        if input_number is None:
            return None

        return [f"EDID hdmiin{input_number} {self._state.edid[input_number]}"]

    def _set_edid(self, match: re.Match[str]) -> list[str] | None:
        """Apply an EDID to an input."""
        input_number = self._input(match.group(1))
        edid = int(match.group(2))

        if input_number is None or edid not in EDID_NAMES:
            return None

        self._state.edid[input_number] = edid

        return [f"EDID hdmiin{input_number} {edid}"]

    def _get_hdcp(self, match: re.Match[str]) -> list[str] | None:
        """Return the HDCP support of an input."""
        input_number = self._input(match.group(1))

        if input_number is None or not self._config.hdcp_supported:
            return None

        state = _on_off(self._state.hdcp[input_number])

        return [f"HDCP_S hdmiin{input_number} {state}"]

    def _set_hdcp(self, match: re.Match[str]) -> list[str] | None:
        """Switch the HDCP support of an input."""
        input_number = self._input(match.group(1))

        if input_number is None or not self._config.hdcp_supported:
            return None

        self._state.hdcp[input_number] = match.group(2).lower() == "on"

        return [f"HDCP_S hdmiin{input_number} {match.group(2).lower()}"]

    def _get_mute(self, match: re.Match[str]) -> list[str] | None:
        """Return the mute state of an audio output."""
        output = self._output(match.group(1))

        if output is None:
            return None

        return [f"MUTE audioout{output} {_on_off(self._state.mute[output])}"]

    def _set_mute(self, match: re.Match[str]) -> list[str] | None:
        """Mute or unmute an audio output."""
        output = self._output(match.group(1))

        if output is None:
            return None

        self._state.mute[output] = match.group(2).lower() == "on"

        return [f"MUTE audioout{output} {match.group(2).lower()}"]

    def _set_mute_all(self, match: re.Match[str]) -> list[str]:
        """Mute or unmute every audio output."""
        muted = match.group(1).lower() == "on"

        for output in self._outputs:
            self._state.mute[output] = muted

        return [f"MUTE all {match.group(1).lower()}"]

    def _get_cec_auto(self, match: re.Match[str]) -> list[str] | None:
        """Return the automatic CEC power function of an output."""
        output = self._output(match.group(1))

        if output is None or not self._config.cec_supported:
            return None

        state = _on_off(self._state.cec_auto[output])

        if self._config.cec_auto_short_reply:
            return [f"AUTOCEC_FN {state}"]

        return [f"AUTOCEC_FN hdmiout{output} {state}"]

    def _set_cec_auto(self, match: re.Match[str]) -> list[str] | None:
        """Switch the automatic CEC power function of an output."""
        output = self._output(match.group(1))

        if output is None or not self._config.cec_supported:
            return None

        self._state.cec_auto[output] = match.group(2).lower() == "on"

        return [f"AUTOCEC_FN hdmiout{output} {match.group(2).lower()}"]

    def _get_cec_delay(self, match: re.Match[str]) -> list[str] | None:
        """Return the automatic CEC power off delay of an output."""
        output = self._output(match.group(1))

        if output is None or not self._config.cec_supported:
            return None

        return [f"AUTOCEC_D hdmiout{output} {self._state.cec_delay[output]}"]

    def _set_cec_delay(self, match: re.Match[str]) -> list[str] | None:
        """Apply the automatic CEC power off delay of an output."""
        output = self._output(match.group(1))
        minutes = int(match.group(2))

        if (
            output is None
            or not self._config.cec_supported
            or not CEC_DELAY_MIN <= minutes <= CEC_DELAY_MAX
        ):
            return None

        self._state.cec_delay[output] = minutes

        return [f"AUTOCEC_D hdmiout{output} {minutes}"]

    def _set_cec_power(self, match: re.Match[str]) -> list[str] | None:
        """Power the sink of an output on or off."""
        output = self._output(match.group(1))

        if output is None or not self._config.cec_supported:
            return None

        self._state.cec_power[output] = match.group(2).lower() == "on"

        return [f"CEC_PWR hdmiout{output} {match.group(2).lower()}"]

    def _set_cec_power_all(self, match: re.Match[str]) -> list[str] | None:
        """Power the sinks of every output on or off."""
        if not self._config.cec_supported:
            return None

        power_on = match.group(1).lower() == "on"

        for output in self._outputs:
            self._state.cec_power[output] = power_on

        return [f"CEC_PWR all {match.group(1).lower()}"]

    def _get_scaler(self, match: re.Match[str]) -> list[str] | None:
        """Return the scaler state of an output."""
        output = self._output(match.group(1))

        if output is None or not self._config.scaler_supported:
            return None

        return [f"SCALER hdmiout{output} {_on_off(self._state.scaler[output])}"]

    def _set_scaler(self, match: re.Match[str]) -> list[str] | None:
        """Switch the scaler of an output."""
        output = self._output(match.group(1))

        if output is None or not self._config.scaler_supported:
            return None

        self._state.scaler[output] = match.group(2).lower() == "on"

        return [f"SCALER hdmiout{output} {match.group(2).lower()}"]

    def _set_scaler_all(self, match: re.Match[str]) -> list[str] | None:
        """Switch the scaler of every output."""
        if not self._config.scaler_supported:
            return None

        enabled = match.group(1).lower() == "on"

        for output in self._outputs:
            self._state.scaler[output] = enabled

        return [f"SCALER all {match.group(1).lower()}"]

    def _save_preset(self, match: re.Match[str]) -> list[str] | None:
        """Store the current routing as a preset scene."""
        preset = int(match.group(1))

        if preset not in self._state.presets:
            return None

        self._state.presets[preset] = dict(self._state.routing)

        return [f"PRESET {preset}"]

    def _restore_preset(self, match: re.Match[str]) -> list[str] | None:
        """Apply the routing of a preset scene."""
        preset = int(match.group(1))

        if preset not in self._state.presets:
            return None

        self._state.routing.update(self._state.presets[preset])

        return [f"PRESET {preset}"]

    def _reset(self, _: re.Match[str]) -> list[str]:
        """Restore the state the matrix leaves the factory with."""
        self._state = MatrixState.factory(self._config)

        _LOGGER.info("The matrix was reset to its factory state")

        return ["RESET"]

    def _reboot(self, _: re.Match[str]) -> list[str]:
        """Acknowledge a reboot, which keeps the state of the matrix."""
        _LOGGER.info("The matrix was rebooted")

        return ["REBOOT"]

    def _upgrade(self, match: re.Match[str]) -> list[str]:
        """Acknowledge a firmware upgrade without changing anything."""
        return [f"UPG {match.group(1).upper()}"]

    def _drift_routing(self) -> str | None:
        """Route a different input to a random output."""
        output = self._random.choice(list(self._outputs))
        choices = [
            number for number in self._inputs if number != self._state.routing[output]
        ]

        if not choices:
            return None

        input_number = self._random.choice(choices)
        self._state.routing[output] = input_number

        return f"input {input_number} is now routed to output {output}"

    def _drift_mute(self) -> str:
        """Toggle the mute state of a random audio output."""
        output = self._random.choice(list(self._outputs))
        muted = not self._state.mute[output]
        self._state.mute[output] = muted

        return f"audio output {output} is now {'muted' if muted else 'unmuted'}"

    def _drift_edid(self) -> str:
        """Apply a different EDID to a random input."""
        input_number = self._random.choice(list(self._inputs))
        choices = [
            value for value in EDID_NAMES if value != self._state.edid[input_number]
        ]
        edid = self._random.choice(choices)
        self._state.edid[input_number] = edid

        return f"input {input_number} now uses EDID {edid} ({EDID_NAMES[edid]})"

    def _drift_hdcp(self) -> str | None:
        """Toggle the HDCP support of a random input."""
        if not self._config.hdcp_supported:
            return None

        input_number = self._random.choice(list(self._inputs))
        enabled = not self._state.hdcp[input_number]
        self._state.hdcp[input_number] = enabled

        return f"HDCP of input {input_number} is now {_on_off(enabled)}"

    def _drift_cec_auto(self) -> str | None:
        """Toggle the automatic CEC power function of a random output."""
        if not self._config.cec_supported:
            return None

        output = self._random.choice(list(self._outputs))
        enabled = not self._state.cec_auto[output]
        self._state.cec_auto[output] = enabled

        return f"auto CEC power of output {output} is now {_on_off(enabled)}"

    def _drift_cec_delay(self) -> str | None:
        """Apply a different CEC power off delay to a random output."""
        if not self._config.cec_supported:
            return None

        output = self._random.choice(list(self._outputs))
        choices = [
            minutes
            for minutes in range(CEC_DELAY_MIN, CEC_DELAY_MAX + 1)
            if minutes != self._state.cec_delay[output]
        ]
        minutes = self._random.choice(choices)
        self._state.cec_delay[output] = minutes

        return f"CEC power off delay of output {output} is now {minutes} minutes"

    def _load_state(self) -> None:
        """Read the stored state, if there is one."""
        if self._state_path is None or not self._state_path.is_file():
            return

        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))

        except (OSError, ValueError) as err:
            _LOGGER.warning("The stored state could not be read: %s", err)

            return

        if isinstance(data, dict):
            self._state.update_from_dict(data)

            _LOGGER.info("The state was restored from %s", self._state_path)

    def _save_state(self) -> None:
        """Write the current state, so it survives a restart."""
        if self._state_path is None:
            return

        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(self._state.as_dict(), indent=2),
                encoding="utf-8",
            )

        except OSError as err:
            _LOGGER.warning("The state could not be stored: %s", err)


def _on_off(value: bool) -> str:
    """Return the word the matrix uses for a boolean."""
    return "on" if value else "off"


def _shorten(text: str, limit: int = 200) -> str:
    """Return a text short enough for a single log line."""
    return text if len(text) <= limit else f"{text[:limit]}..."


def format_response(lines: Iterable[str]) -> bytes:
    """Return the bytes the matrix sends for the lines of an answer.

    The matrix separates the lines of an answer with a single carriage return
    and only terminates the last one with CRLF.
    """
    return ("\r".join(lines) + "\r\n").encode()


class EmulatorServer:
    """Serves the emulated matrix on a TCP port."""

    def __init__(self, matrix: Matrix) -> None:
        """Initialize the server."""
        self._matrix = matrix
        self._config = matrix.config

    async def async_run(self) -> None:
        """Serve until the task is cancelled."""
        server = await asyncio.start_server(
            self._async_handle_client,
            self._config.host,
            self._config.port,
        )

        addresses = ", ".join(
            f"{socket.getsockname()[0]}:{socket.getsockname()[1]}"
            for socket in server.sockets
        )

        _LOGGER.info(
            "The %s emulator with %d inputs and %d outputs listens on %s",
            self._config.model,
            self._config.input_count,
            self._config.output_count,
            addresses,
        )

        async with server:
            await asyncio.gather(server.serve_forever(), self._async_drift())

    async def _async_drift(self) -> None:
        """Change the state of the matrix on its own, as the front panel does."""
        interval = self._config.drift_interval

        if interval <= 0:
            return

        _LOGGER.info("A setting is changed on the matrix itself every %.1f s", interval)

        while True:
            await asyncio.sleep(interval)

            if description := self._matrix.drift():
                _LOGGER.info("Changed at the matrix: %s", description)

    async def _async_handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Answer the commands of a single connection."""
        peer = writer.get_extra_info("peername")

        _LOGGER.debug("%s connected", peer)

        try:
            if self._config.greeting_on_connect:
                writer.write(format_response([self._matrix.greeting]))
                await writer.drain()

            await self._async_serve_commands(reader, writer, peer)

        except (ConnectionError, TimeoutError) as err:
            _LOGGER.debug("%s was disconnected: %s", peer, err)

        finally:
            writer.close()

            with suppress(ConnectionError, OSError):
                await writer.wait_closed()

            _LOGGER.debug("%s disconnected", peer)

    async def _async_serve_commands(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer: object,
    ) -> None:
        """Read commands until the connection ends."""
        while True:
            try:
                line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=self._config.idle_timeout,
                )

            except TimeoutError:
                _LOGGER.debug("%s was idle for too long", peer)

                return

            if not line:
                return

            payload, negotiation = strip_telnet(line)

            if negotiation:
                writer.write(negotiation)
                await writer.drain()

            command = payload.decode("utf-8", "replace").strip()

            if not command:
                continue

            if not await self._async_answer(writer, peer, command):
                continue

            if self._config.close_after_response:
                return

    async def _async_answer(
        self,
        writer: asyncio.StreamWriter,
        peer: object,
        command: str,
    ) -> bool:
        """Answer a single command and return whether the matrix replied."""
        loop = asyncio.get_running_loop()

        if not self._matrix.note_command(loop.time()):
            _LOGGER.warning("%s sent %r while the matrix is busy", peer, command)

            return False

        if self._config.response_delay > 0:
            await asyncio.sleep(self._config.response_delay)

        lines = self._matrix.handle_command(command)

        _LOGGER.info(
            "%s sent %r, answered with %s", peer, command, _shorten(repr(lines))
        )

        writer.write(format_response(lines))
        await writer.drain()

        return True


async def async_main() -> None:
    """Run the emulator."""
    config = Config.from_env()

    logging.basicConfig(
        level=_env_str("AVA_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    await EmulatorServer(Matrix(config)).async_run()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(async_main())
