from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LINES, CONF_STOP_ID, DOMAIN
from .coordinator import LineData, TperConfigEntry, TperDataUpdateCoordinator

# Hello Bus reports the next two buses of a line
MAX_BUSES = 2

# All sensors are updated together by the coordinator
PARALLEL_UPDATES = 0


# Unique id of the sensor for one line at one stop
def sensor_unique_id(stop_id: str, line: str) -> str:
    return f"{DOMAIN}_{stop_id}_{line}"


# Setup function for creating sensor entities
async def async_setup_entry(
    hass: HomeAssistant,
    entry: TperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    lines = entry.options.get(CONF_LINES, [])

    # Remove sensors of lines that are no longer selected
    expected = {sensor_unique_id(entry.data[CONF_STOP_ID], line) for line in lines}
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.domain == "sensor" and entity.unique_id not in expected:
            entity_registry.async_remove(entity.entity_id)

    # Create sensor entity for each configured bus line
    async_add_entities(TperTrackerSensor(coordinator, entry, line) for line in lines)


# Main sensor entity class for TPER bus line tracking
class TperTrackerSensor(CoordinatorEntity[TperDataUpdateCoordinator], SensorEntity):
    _attr_translation_key = "bus_line"
    _attr_icon = "mdi:bus-stop"
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_attribution = "Data provided by TPER (CC BY 3.0 IT)"

    # Initialize sensor with coordinator, config entry, and line code
    def __init__(
        self,
        coordinator: TperDataUpdateCoordinator,
        entry: TperConfigEntry,
        line: str
    ) -> None:
        super().__init__(coordinator)
        self._line = line
        stop_id = entry.data[CONF_STOP_ID]

        # Set unique identifier and translation placeholders
        self._attr_unique_id = sensor_unique_id(stop_id, line)
        self._attr_translation_placeholders = {"line_name": line}

        # Configure device information for grouping sensors
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, stop_id)},
            name=f"TPER Tracker #{stop_id}",
            manufacturer="@ddrimus",
            model="TPER Tracker",
        )

    # Return the next bus arrival time
    @property
    def native_value(self) -> datetime | None:
        line_data = self._get_line_data()
        if not line_data or not line_data.arrivals:
            return None
        return line_data.arrivals[0][0]

    # Provide additional state attributes with bus information
    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        line_data = self._get_line_data()
        if not line_data:
            return None

        attributes: dict[str, Any] = {"line": self._line, "status": line_data.status}

        for i, (_, bus) in enumerate(line_data.arrivals[:MAX_BUSES], 1):
            prefix = f"next_bus_{i}"
            attributes[f"{prefix}_time"] = bus.time
            attributes[f"{prefix}_satellite"] = bus.realtime
            if bus.accessible is not None:
                attributes[f"{prefix}_accessible"] = bus.accessible
            if bus.vehicle:
                attributes[f"{prefix}_vehicle"] = bus.vehicle

        return attributes

    # Get line data from coordinator for this specific line
    def _get_line_data(self) -> LineData | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._line)
