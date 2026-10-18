from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import (
    Arrival,
    HelloBusClient,
    TperApiError,
    TperNotServedError,
    TperRateLimitedError,
)
from .const import (
    CONF_LINES,
    CONF_STOP_ID,
    DOMAIN,
    IDLE_UPDATE_INTERVAL,
    NOT_SERVED_RECHECK,
    TPER_TIME_ZONE,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type TperConfigEntry = ConfigEntry[TperDataUpdateCoordinator]

# Line statuses exposed by the sensors
STATUS_OK = "ok"
STATUS_NO_BUSES = "no_buses"
STATUS_NOT_SERVED = "not_served"
STATUS_ERROR = "error"


# Real-time state of one line at the configured stop
@dataclass(frozen=True)
class LineData:
    status: str
    arrivals: list[tuple[datetime, Arrival]] = field(default_factory=list)


# Convert a Hello Bus arrival time to a datetime, handling predictions across midnight
def resolve_arrival_time(hhmm: str, now: datetime) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when < now - timedelta(hours=6):
        when += timedelta(days=1)
    elif when > now + timedelta(hours=18):
        when -= timedelta(days=1)
    return when


# Main data coordinator class for TPER Hello Bus updates
class TperDataUpdateCoordinator(DataUpdateCoordinator[dict[str, LineData]]):
    config_entry: TperConfigEntry

    # Initialize coordinator with the shared Hello Bus client and configuration
    def __init__(self, hass: HomeAssistant, entry: TperConfigEntry, client: HelloBusClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            # Name the stop in log messages, so several entries can be told apart
            name=f"{DOMAIN} {entry.data[CONF_STOP_ID]}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = client
        self._time_zone: tzinfo = dt_util.get_default_time_zone()
        # Track when each line that is not served should be asked again
        self._not_served: dict[str, float] = {}

    # Resolve the TPER timezone once
    async def _async_setup(self) -> None:
        self._time_zone = await dt_util.async_get_time_zone(TPER_TIME_ZONE) or self._time_zone

    # Calculate dynamic update interval based on the next bus arrival
    def _calculate_dynamic_update_interval(self, lines_data: dict[str, LineData], now: datetime) -> timedelta:
        upcoming = [
            when
            for line_data in lines_data.values()
            for when, _ in line_data.arrivals
            if when > now
        ]
        if not upcoming:
            return timedelta(seconds=IDLE_UPDATE_INTERVAL)

        minutes_until_bus = (min(upcoming) - now).total_seconds() / 60

        if minutes_until_bus <= 5:
            return timedelta(seconds=30)
        elif minutes_until_bus <= 15:
            return timedelta(seconds=60)
        elif minutes_until_bus <= 30:
            return timedelta(seconds=120)
        elif minutes_until_bus <= 60:
            return timedelta(seconds=300)
        elif minutes_until_bus <= 120:
            return timedelta(seconds=600)
        else:
            return timedelta(seconds=900)

    # Main data update method called by coordinator
    async def _async_update_data(self) -> dict[str, LineData]:
        stop_id = self.config_entry.data[CONF_STOP_ID]
        lines = self.config_entry.options.get(CONF_LINES, [])

        lines_data: dict[str, LineData] = {}
        for line in lines:
            # Do not spend the shared request budget on lines TPER does not serve here
            if time.monotonic() < self._not_served.get(line, 0.0):
                lines_data[line] = LineData(STATUS_NOT_SERVED)
                continue

            try:
                arrivals = await self.client.async_get_arrivals(stop_id, line)
            except TperRateLimitedError as err:
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="rate_limited",
                    translation_placeholders={"minutes": str(round(self.client.paused_for / 60) or 1)},
                ) from err
            except TperNotServedError as err:
                _LOGGER.debug("Line %s at stop %s not served: %s", line, stop_id, err)
                self._not_served[line] = time.monotonic() + NOT_SERVED_RECHECK
                lines_data[line] = LineData(STATUS_NOT_SERVED)
                continue
            except TperApiError as err:
                _LOGGER.debug("Failed to update line %s at stop %s: %s", line, stop_id, err)
                lines_data[line] = LineData(STATUS_ERROR)
                continue

            now = dt_util.now(self._time_zone)
            resolved = sorted(
                ((resolve_arrival_time(arrival.time, now), arrival) for arrival in arrivals),
                key=lambda item: item[0],
            )
            lines_data[line] = LineData(STATUS_OK if resolved else STATUS_NO_BUSES, resolved)

        if lines and all(data.status == STATUS_ERROR for data in lines_data.values()):
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"stop_id": stop_id},
            )

        # Update coordinator interval based on bus times
        self.update_interval = self._calculate_dynamic_update_interval(
            lines_data, dt_util.now(self._time_zone)
        )

        return lines_data
