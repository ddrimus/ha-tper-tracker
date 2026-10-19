from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_STOP_ID, CONF_STOP_NAME
from .coordinator import TperConfigEntry

# A chosen bus stop can reveal roughly where the user lives
TO_REDACT = {CONF_STOP_ID, CONF_STOP_NAME, "title", "unique_id"}


# Diagnostics for the config entry, safe to attach to an issue
async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: TperConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
        },
        "hellobus": {
            **coordinator.client.stats,
            "paused_for": round(coordinator.client.paused_for),
        },
        "lines": {
            line: {
                "status": data.status,
                "arrivals": [{"at": when.isoformat(), **asdict(arrival)} for when, arrival in data.arrivals],
            }
            for line, data in (coordinator.data or {}).items()
        },
    }
