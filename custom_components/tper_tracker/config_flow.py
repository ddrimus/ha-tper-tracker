from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import TperApiError
from .const import (
    CONF_ACTIVE_ENTITY,
    CONF_LINES,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
    MAX_LINES,
)
from .sensor import sensor_unique_id
from .stops import Stop, async_get_stop_directory

_LOGGER = logging.getLogger(__name__)

# Entities that can switch polling on and off (a schedule helper covers time windows)
ACTIVE_ENTITY_DOMAINS = ["schedule", "input_boolean", "binary_sensor", "switch"]


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


# Move sensors and the device to a new stop, so entity ids and automations are kept
@callback
def _async_move_to_stop(hass: HomeAssistant, entry: config_entries.ConfigEntry, stop_id: str) -> None:
    old_stop_id = entry.data[CONF_STOP_ID]
    if old_stop_id == stop_id:
        return

    entity_registry = er.async_get(hass)
    prefix = sensor_unique_id(old_stop_id, "")
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.unique_id.startswith(prefix):
            line = entity.unique_id.removeprefix(prefix)
            entity_registry.async_update_entity(entity.entity_id, new_unique_id=sensor_unique_id(stop_id, line))

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if (DOMAIN, old_stop_id) in device.identifiers:
            device_registry.async_update_device(
                device.id, new_identifiers={(DOMAIN, stop_id)}, name=f"TPER Tracker #{stop_id}"
            )


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
        return await self._async_step_search("user", user_input)

    # Reconfigure step: user searches for a different stop, keeping the entry and its entities
    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        return await self._async_step_search("reconfigure", user_input)

    # Shared search step for setup and reconfigure
    async def _async_step_search(self, step_id: str, user_input: dict[str, Any] | None):
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
            step_id=step_id,
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
            if self.source == config_entries.SOURCE_RECONFIGURE:
                # Moving to the current stop is fine, moving to another entry's stop is not
                entry = self._get_reconfigure_entry()
                if any(
                    other.unique_id == self.stop.id and other.entry_id != entry.entry_id
                    for other in self._async_current_entries(include_ignore=False)
                ):
                    return self.async_abort(reason="already_configured")
            else:
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
        reconfigure = self.source == config_entries.SOURCE_RECONFIGURE

        if user_input is not None:
            lines = user_input[CONF_LINES]
            if not _valid_lines(lines):
                errors[CONF_LINES] = "invalid_line_selection"
            else:
                title = f"{self.stop.name} ({self.stop.id})"
                data = {CONF_STOP_ID: self.stop.id, CONF_STOP_NAME: self.stop.name}

                if reconfigure:
                    entry = self._get_reconfigure_entry()
                    _async_move_to_stop(self.hass, entry, self.stop.id)
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=self.stop.id,
                        title=title,
                        data=data,
                        options={**entry.options, CONF_LINES: lines},
                    )

                return self.async_create_entry(title=title, data=data, options={CONF_LINES: lines})

        # When reconfiguring, preselect the current lines that the new stop also serves
        default: list[str] = []
        if reconfigure:
            current = self._get_reconfigure_entry().options.get(CONF_LINES, [])
            default = [line for line in current if line in available]

        return self.async_show_form(
            step_id="select_lines",
            data_schema=_lines_schema(available, default),
            errors=errors,
            description_placeholders={"stop": self.stop.label},
        )


# Options flow handler for modifying existing configuration
class TperTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    # Single step for options: modify selected bus lines and active hours
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
                options: dict[str, Any] = {CONF_LINES: lines}
                if active_entity := user_input.get(CONF_ACTIVE_ENTITY):
                    options[CONF_ACTIVE_ENTITY] = active_entity
                return self.async_create_entry(title="", data=options)

        schema = _lines_schema(available, current).extend({
            vol.Optional(CONF_ACTIVE_ENTITY): EntitySelector(
                EntitySelectorConfig(domain=ACTIVE_ENTITY_DOMAINS)
            )
        })
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
            errors=errors,
        )
