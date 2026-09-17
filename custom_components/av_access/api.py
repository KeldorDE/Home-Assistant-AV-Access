"""API client for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import INPUT_COUNT, OUTPUT_COUNT


class AVAccessApiError(Exception):
    """Base exception for AV Access API errors."""


class AVAccessConnectionError(AVAccessApiError):
    """Exception raised when the controller cannot be reached."""


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

    async def get_status(self) -> dict[str, Any]:
        """Return the current matrix state."""
        data = await self._request(
            "GET",
            "/status",
        )

        try:
            return {
                "outputs": {
                    str(i): int(data[f"out{i}_in"]) for i in range(1, OUTPUT_COUNT + 1)
                },
                "edid": {
                    str(i): int(data[f"edid_in{i}"]) for i in range(1, INPUT_COUNT + 1)
                },
            }
        except (KeyError, TypeError, ValueError) as err:
            raise AVAccessApiError(f"Unexpected status payload: {data}") from err

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
