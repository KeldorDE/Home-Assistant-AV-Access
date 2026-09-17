"""API client for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import re
from typing import Any, TypedDict

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import (
    DEFAULT_INPUT_COUNT,
    DEFAULT_OUTPUT_COUNT,
    SSE_READ_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

# Name of the SSE event carrying the full matrix state.
STATE_EVENT = "state"

# The status payload reports one entry per output and per input.
OUTPUT_KEY_PATTERN = re.compile(r"out(\d+)_in")
EDID_KEY_PATTERN = re.compile(r"edid_in(\d+)")
HDCP_KEY_PATTERN = re.compile(r"hdcp_in(\d+)")

# Accepted by the controller and therefore also understood when reported.
TRUE_VALUES = frozenset({"true", "on", "enable", "yes", "1"})
FALSE_VALUES = frozenset({"false", "off", "disable", "no", "0"})


class AVAccessStatus(TypedDict):
    """Current routing state of the matrix, keyed by port number."""

    outputs: dict[str, int]
    edid: dict[str, int]
    hdcp: dict[str, bool]


class AVAccessApiError(Exception):
    """Base exception for AV Access API errors."""


class AVAccessConnectionError(AVAccessApiError):
    """Exception raised when the controller cannot be reached."""


class AVAccessEventsNotSupportedError(AVAccessApiError):
    """Exception raised when the controller does not offer an event stream."""


def _parse_status(data: Any) -> AVAccessStatus:
    """Build the matrix state from a status payload.

    The same payload is returned by ``GET /status`` and by the ``state`` events
    of the controller, so both paths share this function.
    """
    if not isinstance(data, dict):
        raise AVAccessApiError(f"Unexpected status payload: {data}")

    outputs: dict[str, int] = {}
    edid: dict[str, int] = {}
    hdcp: dict[str, bool] = {}

    # The number of ports depends on the model, so every reported entry is
    # taken as it comes instead of expecting a fixed range. A matrix without
    # HDCP support reports no HDCP entries at all.
    try:
        for key, value in data.items():
            if match := OUTPUT_KEY_PATTERN.fullmatch(key):
                outputs[match.group(1)] = int(value)

            elif match := EDID_KEY_PATTERN.fullmatch(key):
                edid[match.group(1)] = int(value)

            elif match := HDCP_KEY_PATTERN.fullmatch(key):
                hdcp[match.group(1)] = _as_bool(value)

    except (TypeError, ValueError) as err:
        raise AVAccessApiError(f"Unexpected status payload: {data}") from err

    return {
        "outputs": outputs,
        "edid": edid,
        "hdcp": hdcp,
    }


def _as_str(value: Any) -> str | None:
    """Return a non-empty string, or None."""
    if not isinstance(value, str) or not value.strip():
        return None

    return value.strip()


def _as_count(value: Any, default: int) -> int:
    """Return a positive port count, or the given default."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return default

    return count if count > 0 else default


def _as_bool(value: Any) -> bool:
    """Return a boolean from the formats the controller accepts."""
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in TRUE_VALUES:
            return True

        if normalized in FALSE_VALUES:
            return False

    raise ValueError(f"Unexpected HDCP value: {value!r}")


def _as_datetime(value: Any) -> datetime | None:
    """Return a timezone aware datetime, or None."""
    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True, kw_only=True)
class AVAccessDeviceInfo:
    """Static information reported by the controller about the matrix."""

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

    @classmethod
    def from_payload(cls, data: Any) -> AVAccessDeviceInfo:
        """Build the device information from an API payload."""
        if not isinstance(data, dict):
            raise AVAccessApiError(f"Unexpected device info payload: {data}")

        unique_id = _as_str(data.get("unique_id"))

        if unique_id is None:
            raise AVAccessApiError("Device info payload does not contain a unique ID")

        return cls(
            unique_id=unique_id,
            model=_as_str(data.get("model")),
            manufacturer=_as_str(data.get("manufacturer")),
            sw_version=_as_str(data.get("sw_version")),
            hw_version=_as_str(data.get("hw_version")),
            arm_version=_as_str(data.get("arm_version")),
            configuration_url=_as_str(data.get("configuration_url")),
            ip_address=_as_str(data.get("ip_address")),
            netmask=_as_str(data.get("netmask")),
            gateway=_as_str(data.get("gateway")),
            ip_mode=_as_str(data.get("ip_mode")),
            input_count=_as_count(data.get("input_count"), DEFAULT_INPUT_COUNT),
            output_count=_as_count(data.get("output_count"), DEFAULT_OUTPUT_COUNT),
            updated_at=_as_datetime(data.get("updated_at")),
        )


class AVAccessApiClient:
    """Client for the AV Access HDMI-Matrix Controller API."""

    def __init__(
        self,
        host: str,
        port: int,
        session: ClientSession,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._base_url = f"http://{host}:{port}"

    async def get_device_info(self) -> AVAccessDeviceInfo:
        """Return static information about the connected matrix."""
        return AVAccessDeviceInfo.from_payload(
            await self._request(
                "GET",
                "/device-info",
            )
        )

    async def get_status(self) -> AVAccessStatus:
        """Return the current matrix state."""
        return _parse_status(
            await self._request(
                "GET",
                "/status",
            )
        )

    async def subscribe_events(self) -> AsyncIterator[AVAccessStatus]:
        """Yield the matrix state whenever the controller reports a change.

        The controller sends the currently cached state right after connecting,
        so a consumer is in sync as soon as the stream is established.
        """
        url = f"{self._base_url}/events"

        try:
            async with self._session.get(
                url,
                headers={"Accept": "text/event-stream"},
                # A stream stays open, so the regular request timeout must not
                # apply. Only a silent connection is treated as dead.
                timeout=ClientTimeout(
                    total=None,
                    sock_connect=10,
                    sock_read=SSE_READ_TIMEOUT,
                ),
            ) as response:
                if response.status == 404:
                    raise AVAccessEventsNotSupportedError(
                        f"The controller at {self._base_url} does not provide an "
                        f"event stream"
                    )

                response.raise_for_status()

                event_name = ""
                data_lines: list[str] = []

                async for raw_line in response.content:
                    line = raw_line.decode("utf-8", "replace").rstrip("\r\n")

                    # An empty line terminates the current frame.
                    if not line:
                        if status := self._parse_event(event_name, data_lines):
                            yield status

                        event_name = ""
                        data_lines = []
                        continue

                    # Lines starting with a colon are comments, for example the
                    # keepalive of the controller.
                    if line.startswith(":"):
                        continue

                    field, _, value = line.partition(":")

                    if value.startswith(" "):
                        value = value[1:]

                    if field == "event":
                        event_name = value

                    elif field == "data":
                        data_lines.append(value)

                    # The "id" and "retry" fields are not needed, because every
                    # event carries the complete state.

        except ClientResponseError as err:
            if err.status == 404:
                raise AVAccessEventsNotSupportedError(
                    f"The controller at {self._base_url} does not provide an "
                    f"event stream"
                ) from err

            raise AVAccessApiError(
                f"Event stream failed with HTTP {err.status}: {err.message}"
            ) from err

        except (ClientError, TimeoutError) as err:
            raise AVAccessConnectionError(
                f"Event stream of the AV Access HDMI-Matrix Controller at "
                f"{self._base_url} was interrupted: {err}"
            ) from err

    @staticmethod
    def _parse_event(
        event_name: str,
        data_lines: list[str],
    ) -> AVAccessStatus | None:
        """Return the state of a completed SSE frame, if it carries one."""
        if event_name != STATE_EVENT or not data_lines:
            return None

        payload = "\n".join(data_lines)

        # A single malformed message must not tear down the stream.
        try:
            return _parse_status(json.loads(payload))

        except (ValueError, AVAccessApiError):
            _LOGGER.debug("Ignoring malformed state event: %s", payload)

            return None

    async def set_output(
        self,
        output_number: int,
        input_number: int,
    ) -> None:
        """Route an HDMI input to an output."""
        await self._request(
            "POST",
            "/switch",
            json={
                "input": input_number,
                "output": output_number,
            },
        )

    async def set_edid(
        self,
        input_number: int,
        edid: int,
    ) -> None:
        """Set the EDID for an HDMI input."""
        await self._request(
            "POST",
            "/edid",
            json={
                "input": input_number,
                "edid": edid,
            },
        )

    async def set_hdcp(
        self,
        input_number: int,
        enabled: bool,
    ) -> None:
        """Enable or disable HDCP support for an HDMI input."""
        await self._request(
            "POST",
            "/switch/hdcp",
            json={
                "input": input_number,
                "hdcp": enabled,
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Perform an API request."""
        url = f"{self._base_url}{path}"

        try:
            async with self._session.request(
                method,
                url,
                timeout=ClientTimeout(total=10),
                **kwargs,
            ) as response:
                response.raise_for_status()

                if response.status == 204:
                    return None

                if response.content_type == "application/json":
                    return await response.json()

                return await response.text()

        except ClientResponseError as err:
            raise AVAccessApiError(
                f"API request failed with HTTP {err.status}: {err.message}"
            ) from err

        except ClientError as err:
            raise AVAccessConnectionError(
                f"Unable to connect to AV Access HDMI-Matrix Controller at "
                f"{self._base_url}"
            ) from err
