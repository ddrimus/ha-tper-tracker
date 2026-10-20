from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import CONF_LINES
from .coordinator import STATUS_NOT_SERVED


# Fix flow that stops tracking the lines Hello Bus does not serve at the stop
class LinesNotServedRepairFlow(RepairsFlow):
    # Initialize fix flow for the config entry
    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    # Initial step: go straight to the confirmation
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return await self.async_step_confirm()

    # Confirm step: user agrees to stop tracking the lines not served
    async def async_step_confirm(self, user_input: dict[str, Any] | None = None):
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        data = entry.runtime_data.data or {}
        not_served = [line for line, line_data in data.items() if line_data.status == STATUS_NOT_SERVED]
        keep = [line for line in entry.options.get(CONF_LINES, []) if line not in not_served]
        if not keep:
            return self.async_abort(reason="no_lines_left")

        if user_input is not None:
            self.hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_LINES: keep})
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"title": entry.title, "lines": ", ".join(not_served)},
        )


# Create the fix flow for the only fixable issue, the lines not served
async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    assert data is not None
    return LinesNotServedRepairFlow(str(data["entry_id"]))
