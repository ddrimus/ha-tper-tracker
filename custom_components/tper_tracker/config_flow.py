from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import TperApiError
from .const import (
    CONF_LINES,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
    MAX_LINES,
)
from .stops import Stop, async_get_stop_directory

_LOGGER = logging.getLogger(__name__)


# Validation function for the selected lines (the selector already rejects unknown lines)
def _valid_lines(lines: list[str]) -> bool:
    return 1 <= len(lines) <= MAX_LINES


# Build the multi-select schema used to pick lines
def _lines_schema(available: list[str], default: list[str]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_LINES, default=default): SelectSelector(
            SelectSelectorConfig(
                options=[SelectOptionDict(value=line, label=line) for line in available],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
    })


# Main configuration flow class for TPER Tracker setup
class TperTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    # Initialize flow state for the search results and the selected stop
    def __init__(self) -> None:
        self.stops: list[Stop] = []
        self.stop: Stop | None = None

    # Create options flow handler for configuration changes
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TperTrackerOptionsFlowHandler:
        return TperTrackerOptionsFlowHandler()

    # Initial step: user enters stop search query
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            query = user_input["stop_query"].strip()
            if not query:
                errors["stop_query"] = "invalid_query"
            else:
                directory = async_get_stop_directory(self.hass)
                try:
                    await directory.async_ensure_loaded()
                except TperApiError as err:
                    _LOGGER.warning("Could not download the TPER stop list: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    self.stops = directory.search(query)
                    if not self.stops:
                        errors["base"] = "no_stops_found"
                    else:
                        return await self.async_step_select_stop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("stop_query"): str
            }),
            errors=errors,
        )

    # Second step: user selects a specific stop from search results
    async def async_step_select_stop(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            # The selector only accepts stops from the search results
            self.stop = next(stop for stop in self.stops if stop.id == user_input[CONF_STOP_ID])
            await self.async_set_unique_id(self.stop.id)
            self._abort_if_unique_id_configured()
            return await self.async_step_select_lines()

        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=stop.id, label=stop.label)
                            for stop in self.stops
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }),
        )

    # Final step: user selects which bus lines to track
    async def async_step_select_lines(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        assert self.stop is not None
        available = list(self.stop.lines)

        if user_input is not None:
            lines = user_input[CONF_LINES]
            if not _valid_lines(lines):
                errors[CONF_LINES] = "invalid_line_selection"
            else:
                title = f"{self.stop.name} ({self.stop.id})"
                data = {CONF_STOP_ID: self.stop.id, CONF_STOP_NAME: self.stop.name}
                return self.async_create_entry(title=title, data=data, options={CONF_LINES: lines})

        return self.async_show_form(
            step_id="select_lines",
            data_schema=_lines_schema(available, []),
            errors=errors,
            description_placeholders={"stop": self.stop.label},
        )


# Options flow handler for modifying existing configuration
class TperTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    # Single step for options: modify selected bus lines
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        stop_id = self.config_entry.data[CONF_STOP_ID]
        current = list(self.config_entry.options.get(CONF_LINES, []))

        directory = async_get_stop_directory(self.hass)
        try:
            await directory.async_ensure_loaded()
        except TperApiError as err:
            _LOGGER.warning("Could not download the TPER stop list: %s", err)
            return self.async_abort(reason="cannot_connect")

        # Keep configured lines selectable even if TPER no longer lists them here
        stop = directory.get(stop_id)
        available = list(dict.fromkeys([*(stop.lines if stop else ()), *current]))

        if user_input is not None:
            lines = user_input[CONF_LINES]
            if not _valid_lines(lines):
                errors[CONF_LINES] = "invalid_line_selection"
            else:
                return self.async_create_entry(title="", data={CONF_LINES: lines})

        return self.async_show_form(
            step_id="init",
            data_schema=_lines_schema(available, current),
            errors=errors,
        )
