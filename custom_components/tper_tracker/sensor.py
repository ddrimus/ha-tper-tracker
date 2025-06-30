from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_LINE_IDS,
    CONF_LINE_NAMES,
    CONF_STOP_ID,
    DOMAIN,
)
from .coordinator import TperDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


# Setup function for creating sensor entities
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    # Get coordinator and line IDs from configuration
    coordinator: TperDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    line_ids = entry.options.get(CONF_LINE_IDS, entry.data.get(CONF_LINE_IDS, []))
    
    # Create sensor entity for each configured bus line
    entities = [
        TperTrackerSensor(coordinator, entry, line_id)
        for line_id in line_ids
    ]
    
    async_add_entities(entities)


# Main sensor entity class for TPER bus line tracking
class TperTrackerSensor(CoordinatorEntity[TperDataUpdateCoordinator], SensorEntity):
    _attr_translation_key = "bus_line"
    _attr_icon = "mdi:bus-stop"
    _attr_has_entity_name = True

    # Initialize sensor with coordinator, config entry, and line ID
    def __init__(
        self, 
        coordinator: TperDataUpdateCoordinator, 
        entry: ConfigEntry, 
        line_id: str
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._line_id = line_id
        
        # Extract line and stop information from configuration
        line_names = entry.options.get(CONF_LINE_NAMES, entry.data.get(CONF_LINE_NAMES, {}))
        line_name = line_names.get(line_id, line_id)
        stop_id = entry.data[CONF_STOP_ID]
        stop_name = entry.title
        
        # Set unique identifier and translation placeholders
        self._attr_unique_id = f"{DOMAIN}_{stop_id}_{line_id}"
        self._attr_translation_placeholders = {
            "line_name": line_name,
            "stop_name": stop_name,
            "stop_id": str(stop_id),
        }
        
        # Configure device information for grouping sensors
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(stop_id))},
            name=f"TPER Tracker #{stop_id}",
            manufacturer="@ddrimus",
            model="TPER Tracker",
        )

    # Return the sensor's native value (next bus time or error state)
    @property
    def native_value(self) -> datetime | str | None:
        line_data = self._get_line_data()
        if not line_data:
            return None
        
        # Return error state if present
        if error := line_data.get("error"):
            return error

        # Parse and return next bus arrival time
        if risultati := line_data.get("risultati"):
            time_str = risultati[0]["orario"]
            return self._parse_time_to_datetime(time_str)
        
        return None

    # Determine appropriate device class based on data type
    @property
    def device_class(self) -> SensorDeviceClass | None:
        line_data = self._get_line_data()
        if not line_data or line_data.get("error"):
            return None
        return SensorDeviceClass.TIMESTAMP if line_data.get("risultati") else None

    # Check if sensor data is available (not in API error state)
    @property
    def available(self) -> bool:
        line_data = self._get_line_data()
        return line_data and line_data.get("error") != "api_error"

    # Provide additional state attributes with bus information
    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        line_data = self._get_line_data()
        if not line_data:
            return None

        attributes = {}

        # Add error information if present
        if error := line_data.get("error"):
            attributes["error"] = error
            if error == "api_error":
                return attributes

        # Add last update time and line information
        if info := line_data.get("info", {}):
            if valido := info.get("valido"):
                last_update = (
                    valido.split("Aggiornato alle ore ")[1] 
                    if "Aggiornato alle ore " in valido 
                    else valido
                )
                attributes["last_update"] = last_update
            if linea := info.get("linea"):
                attributes["line"] = linea

        # Add information for next 3 buses
        if risultati := line_data.get("risultati", []):
            for i, bus in enumerate(risultati[:3], 1):
                prefix = f"next_bus_{i}"
                
                # Add bus arrival time
                if orario := bus.get("orario"):
                    attributes[f"{prefix}_time"] = orario
                
                # Add GPS tracking status
                if satellite := bus.get("satellite"):
                    attributes[f"{prefix}_satellite"] = satellite
                
                # Add accessibility information
                if pedana := bus.get("pedana"):
                    attributes[f"{prefix}_accessible"] = pedana

        return attributes

    # Get line data from coordinator for this specific line
    def _get_line_data(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        
        lines_data = self.coordinator.data.get("lines", {})
        return lines_data.get(self._line_id)

    # Parse time string to datetime with proper date handling
    def _parse_time_to_datetime(self, time_str: str) -> datetime | None:
        try:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
            now = dt_util.now()
            today = now.date()
            
            # Create datetime object with local timezone
            bus_datetime = dt_util.as_local(datetime.combine(today, time_obj))
            
            # Handle day rollover for past times or overnight service
            if bus_datetime < now:
                current_hour = now.hour
                bus_hour = time_obj.hour
                
                # Check for overnight service transition or significantly past times
                if (current_hour >= 22 and bus_hour <= 6) or bus_datetime < now - timedelta(minutes=5):
                    bus_datetime += timedelta(days=1)
            
            return bus_datetime
        except ValueError:
            _LOGGER.warning("Failed to parse time '%s' for sensor %s", time_str, self._attr_unique_id)
            return None