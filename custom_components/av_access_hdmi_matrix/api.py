"""API client for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession


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
        return await self._request(
            "GET",
            "/api/status",
        )

    async def set_output(
        self,
        output: int,
        input_number: int,
    ) -> None:
        """Route an HDMI input to an output."""
        await self._request(
            "POST",
            f"/api/outputs/{output}",
            json={
                "input": input_number,
            },
        )

    async def set_edid(
        self,
        input_number: int,
        edid: str,
    ) -> None:
        """Set the EDID for an HDMI input."""
        await self._request(
            "POST",
            f"/api/inputs/{input_number}/edid",
            json={
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
                timeout=10,
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
