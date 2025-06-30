from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .api import (
    TperApiClient,
    TperApiError,
    TperApiNoMoreBusesError,
    TperApiRealTimeNotAvailableError,
    TperApiSystemError,
)
from .const import (
    CONF_LINE_IDS,
    CONF_STOP_ID,
    DOMAIN,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


# Main data coordinator class for TPER API updates
class TperDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    # Initialize coordinator with API client and configuration
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.api_client = TperApiClient(async_get_clientsession(hass))
        self.config_entry = entry
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    # Calculate dynamic update interval based on next bus arrival times
    def _calculate_dynamic_update_interval(self, lines_data: dict[str, Any]) -> timedelta:
        earliest_bus_time = None
        current_time = dt_util.now()
        
        # Find the earliest bus arrival time across all lines
        for line_data in lines_data.values():
            if line_data.get("error") or not line_data.get("risultati"):
                continue
                
            try:
                time_str = line_data["risultati"][0]["orario"]
                bus_time = self._parse_time_to_datetime(time_str)
                
                if bus_time and bus_time > current_time:
                    if earliest_bus_time is None or bus_time < earliest_bus_time:
                        earliest_bus_time = bus_time
            except (KeyError, ValueError, IndexError):
                continue
        
        # Return default interval if no valid bus time found
        if earliest_bus_time is None:
            return timedelta(seconds=UPDATE_INTERVAL)
        
        # Calculate time until next bus and set appropriate update frequency
        time_until_bus = earliest_bus_time - current_time
        minutes_until_bus = time_until_bus.total_seconds() / 60
        
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

    # Parse time string (HH:MM) to datetime object with proper date handling
    def _parse_time_to_datetime(self, time_str: str) -> datetime | None:
        try:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
            
            now = dt_util.now()
            today = now.date()
            
            # Combine date and time to create full datetime
            bus_datetime = datetime.combine(today, time_obj)
            bus_datetime = dt_util.as_local(bus_datetime)
            
            # Handle day rollover for late night and early morning buses
            if bus_datetime < now:
                current_hour = now.hour
                bus_hour = time_obj.hour
                
                # Check for overnight service or past times
                if current_hour >= 22 and bus_hour <= 6:
                    bus_datetime = bus_datetime + timedelta(days=1)
                elif bus_datetime < now - timedelta(minutes=5):
                    bus_datetime = bus_datetime + timedelta(days=1)
            
            return bus_datetime
            
        except ValueError:
            return None

    # Main data update method called by coordinator
    async def _async_update_data(self) -> dict[str, Any]:
        # Get configuration data for stop and lines
        stop_id = self.config_entry.data[CONF_STOP_ID]
        line_ids = self.config_entry.options.get(
            CONF_LINE_IDS, 
            self.config_entry.data.get(CONF_LINE_IDS, [])
        )
        
        line_ids_int = [int(line_id) for line_id in line_ids]
        
        try:
            # Attempt concurrent data fetch for all lines
            lines_data_raw = await self.api_client.async_get_multiple_real_time_data(
                stop_id, line_ids_int, max_concurrent=2
            )
            
            lines_data = {}
            
            # Process each line's data and handle errors
            for line_id, line_data in lines_data_raw.items():
                if isinstance(line_data.get("error"), str):
                    error_msg = line_data["error"]
                    if "Informazioni in tempo reale non disponibili" in error_msg:
                        lines_data[line_id] = {"error": "not_available"}
                    elif "prevista nessun'altra corsa" in error_msg:
                        lines_data[line_id] = {"error": "no_more_buses"}
                    elif "qualche problema con il sistema di informazioni in tempo reale" in error_msg:
                        lines_data[line_id] = {"error": "system_error"}
                    else:
                        lines_data[line_id] = {"error": "api_error"}
                else:
                    lines_data[line_id] = line_data
                        
        except TperApiError:
            # Fallback to individual requests if concurrent fetch fails
            lines_data = {}
            
            for line_id in line_ids:
                try:
                    line_data = await self.api_client.async_get_real_time_data(
                        stop_id, int(line_id)
                    )
                    lines_data[line_id] = line_data
                except TperApiRealTimeNotAvailableError:
                    lines_data[line_id] = {"error": "not_available"}
                except TperApiNoMoreBusesError:
                    lines_data[line_id] = {"error": "no_more_buses"}
                except TperApiSystemError:
                    lines_data[line_id] = {"error": "system_error"}
                except TperApiError:
                    lines_data[line_id] = {"error": "api_error"}

        # Update coordinator interval based on bus times
        new_interval = self._calculate_dynamic_update_interval(lines_data)
        if new_interval != self.update_interval:
            self.update_interval = new_interval

        return {"lines": lines_data}