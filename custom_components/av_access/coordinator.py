"""Data update coordinator for the AV Access HDMI-Matrix integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    AVAccessApiClient,
    AVAccessApiError,
    AVAccessConnectionError,
    AVAccessDeviceInfo,
    AVAccessEventsNotSupportedError,
    AVAccessStatus,
)
from .const import (
    DOMAIN,
    SSE_RECONNECT_INTERVAL,
    SSE_RECONNECT_MAX_INTERVAL,
    UPDATE_INTERVAL,
)

if TYPE_CHECKING:
    from . import AVAccessConfigEntry

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=UPDATE_INTERVAL)


class AVAccessCoordinator(DataUpdateCoordinator[AVAccessStatus]):
    """Coordinate data updates from the AV Access HDMI-Matrix Controller."""

    config_entry: AVAccessConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: AVAccessApiClient,
        config_entry: AVAccessConfigEntry,
        device_info: AVAccessDeviceInfo,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="AV Access Matrix",
            update_interval=POLL_INTERVAL,
        )

        self.client = client

        # The static device information is read once while setting up the entry.
        self.device_info = device_info

        self._push_active = False

    @property
    def push_active(self) -> bool:
        """Return whether the state is currently received via the event stream."""
        return self._push_active

    @callback
    def async_start_event_listener(self) -> None:
        """Listen for state events until the config entry is unloaded."""
        self.config_entry.async_create_background_task(
            self.hass,
            self._async_listen_events(),
            name=f"{DOMAIN} event listener",
            eager_start=True,
        )

    async def async_refresh_after_command(self) -> None:
        """Refresh the state after a command, unless events are received.

        The controller emits a state event right after a successful command, so
        an extra status request is only needed while polling.
        """
        if self._push_active:
            return

        await self.async_request_refresh()

    async def _async_listen_events(self) -> None:
        """Consume the event stream and reconnect when it breaks."""
        delay = SSE_RECONNECT_INTERVAL

        while True:
            try:
                async for status in self.client.subscribe_events():
                    # The stream delivers the full state, so the first event
                    # after (re)connecting brings the integration back in sync.
                    self._async_set_push_active(True)
                    delay = SSE_RECONNECT_INTERVAL

                    self.async_set_updated_data(status)

                _LOGGER.debug("Event stream closed by the controller")

            except AVAccessEventsNotSupportedError:
                # An older controller has no event stream, so polling stays the
                # only way to receive updates.
                _LOGGER.info(
                    "The AV Access HDMI-Matrix Controller does not support event "
                    "streaming, falling back to polling every %s seconds",
                    UPDATE_INTERVAL,
                )
                self._async_set_push_active(False)

                return

            except asyncio.CancelledError:
                # The config entry is unloading, so no rescheduling is wanted.
                raise

            except AVAccessConnectionError as err:
                _LOGGER.debug("Event stream connection lost: %s", err)

            except AVAccessApiError as err:
                _LOGGER.warning("Event stream failed: %s", err)

            # Polling takes over until the stream is available again.
            if self._async_set_push_active(False):
                # Setting the interval alone does not reschedule the timer.
                await self.async_refresh()

            await asyncio.sleep(delay)

            delay = min(delay * 2, SSE_RECONNECT_MAX_INTERVAL)

    @callback
    def _async_set_push_active(self, active: bool) -> bool:
        """Enable or disable polling depending on the event stream state.

        Returns whether the mode actually changed.
        """
        if self._push_active == active:
            return False

        self._push_active = active

        # Polling is only a fallback while no events are received.
        self.update_interval = None if active else POLL_INTERVAL

        _LOGGER.debug(
            "Receiving matrix state via %s",
            "events" if active else "polling",
        )

        return True

    async def _async_update_data(self) -> AVAccessStatus:
        """Fetch the latest matrix state."""
        try:
            return await self.client.get_status()

        except AVAccessConnectionError as err:
            raise UpdateFailed(
                f"Unable to connect to AV Access HDMI-Matrix Controller: {err}"
            ) from err

        except AVAccessApiError as err:
            raise UpdateFailed(
                f"Error communicating with AV Access HDMI-Matrix Controller: {err}"
            ) from err
