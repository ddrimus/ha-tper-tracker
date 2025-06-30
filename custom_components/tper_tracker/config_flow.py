from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import TperApiClient, TperApiError
from .const import (
    CONF_LINE_IDS,
    CONF_LINE_NAMES,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


# Validation function for stop search query
def _validate_stop_query(query: str) -> str:
    if not query or not query.strip():
        raise vol.Invalid("Search query cannot be empty")
    
    query = query.strip()
    if len(query) > 200:
        raise vol.Invalid("Search query too long")
    
    return query


# Validation function for stop ID
def _validate_stop_id(stop_id_str: str) -> str:
    try:
        stop_id = int(stop_id_str)
        if stop_id <= 0 or stop_id > 999999:
            raise vol.Invalid("Invalid stop ID range")
        return stop_id_str
    except ValueError:
        raise vol.Invalid("Stop ID must be a valid number")


# Validation function for line IDs list
def _validate_line_ids(line_ids: list[str]) -> list[str]:
    if not line_ids:
        raise vol.Invalid("At least one line must be selected")
    
    if len(line_ids) > 20:
        raise vol.Invalid("Too many lines selected (max 20)")
    
    validated_ids = []
    for line_id in line_ids:
        try:
            line_id_int = int(line_id)
            if line_id_int <= 0 or line_id_int > 999999:
                raise vol.Invalid(f"Invalid line ID: {line_id}")
            validated_ids.append(line_id)
        except ValueError:
            raise vol.Invalid(f"Line ID must be a valid number: {line_id}")
    
    return validated_ids


# Main configuration flow class for TPER Tracker setup
class TperTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    
    def __init__(self) -> None:
        self.api_client: TperApiClient | None = None
        self.data: dict[str, Any] = {}
        self.stops: list[dict[str, Any]] = []
        self.lines: list[dict[str, Any]] = []

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
            try:
                query = _validate_stop_query(user_input["stop_query"])
                
                # Initialize API client and search for stops
                session = async_get_clientsession(self.hass)
                self.api_client = TperApiClient(session)
                
                try:
                    self.stops = await self.api_client.async_search_stops(query)
                    if not self.stops:
                        errors["base"] = "no_stops_found"
                    else:
                        return await self.async_step_select_stop()
                except TperApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "unknown"
                    
            except vol.Invalid:
                errors["stop_query"] = "invalid_query"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("stop_query"): str
            }),
            errors=errors,
        )

    # Second step: user selects a specific stop from search results
    async def async_step_select_stop(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                stop_id_str = _validate_stop_id(user_input[CONF_STOP_ID])
                stop_id = int(stop_id_str)
                
                # Store selected stop data
                self.data[CONF_STOP_ID] = stop_id
                
                selected_stop = next(
                    (stop for stop in self.stops if stop["id"] == stop_id), None
                )
                if selected_stop:
                    self.data[CONF_STOP_NAME] = selected_stop["head"]
                
                # Fetch available lines for the selected stop
                if self.api_client:
                    try:
                        self.lines = await self.api_client.async_get_stop_lines(stop_id)
                        if not self.lines:
                            errors["base"] = "no_lines_found"
                        else:
                            return await self.async_step_select_lines()
                    except TperApiError:
                        errors["base"] = "cannot_connect"
                    except Exception:
                        errors["base"] = "unknown"
                else:
                    errors["base"] = "unknown"
                    
            except vol.Invalid:
                errors[CONF_STOP_ID] = "invalid_stop_id"

        # Create dropdown options for stop selection
        stop_options = [
            SelectOptionDict(
                value=str(stop["id"]), 
                label=f'{stop["head"]} ({stop["body"]})'
            ) 
            for stop in self.stops
        ]

        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema({
                vol.Required(CONF_STOP_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=stop_options, 
                        mode=SelectSelectorMode.DROPDOWN
                    )
                )
            }),
            errors=errors,
        )

    # Final step: user selects which bus lines to track
    async def async_step_select_lines(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                line_ids = _validate_line_ids(user_input[CONF_LINE_IDS])
                
                # Build line names mapping for selected lines
                line_names = {
                    str(line["idLinea"]): line["codiceLinea"] 
                    for line in self.lines
                }
                selected_line_names = {
                    line_id: line_names[line_id] 
                    for line_id in line_ids
                }

                # Set unique ID and create the configuration entry
                await self.async_set_unique_id(str(self.data[CONF_STOP_ID]))
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=self.data[CONF_STOP_NAME], 
                    data=self.data,
                    options={
                        CONF_LINE_IDS: line_ids,
                        CONF_LINE_NAMES: selected_line_names,
                    }
                )
                
            except vol.Invalid:
                errors[CONF_LINE_IDS] = "invalid_line_selection"

        # Create list options for line selection
        line_options = [
            SelectOptionDict(
                value=str(line["idLinea"]), 
                label=line["codiceLinea"]
            ) 
            for line in self.lines
        ]

        return self.async_show_form(
            step_id="select_lines",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_LINE_IDS,
                    default=self.data.get(CONF_LINE_IDS, []),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=line_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }),
            errors=errors,
        )


# Options flow handler for modifying existing configuration
class TperTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = []
        self.api_client: TperApiClient | None = None

    # Single step for options: modify selected bus lines
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                line_ids = _validate_line_ids(user_input[CONF_LINE_IDS])
                
                # Build updated line names mapping
                line_names = {
                    str(line["idLinea"]): line["codiceLinea"] 
                    for line in self.lines
                }
                selected_line_names = {
                    line_id: line_names[line_id] 
                    for line_id in line_ids
                }

                return self.async_create_entry(
                    title="", 
                    data={
                        CONF_LINE_IDS: line_ids,
                        CONF_LINE_NAMES: selected_line_names,
                    }
                )
                
            except vol.Invalid:
                errors[CONF_LINE_IDS] = "invalid_line_selection"

        # Fetch current lines for the configured stop
        session = async_get_clientsession(self.hass)
        self.api_client = TperApiClient(session)
        stop_id = self.config_entry.data[CONF_STOP_ID]
        
        try:
            self.lines = await self.api_client.async_get_stop_lines(stop_id)
        except TperApiError:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            return self.async_abort(reason="cannot_connect")

        # Create options for line selection
        line_options = [
            SelectOptionDict(
                value=str(line["idLinea"]), 
                label=line["codiceLinea"]
            )
            for line in self.lines
        ]

        # Get currently selected lines
        current_line_ids = self.config_entry.options.get(
            CONF_LINE_IDS, 
            self.config_entry.data.get(CONF_LINE_IDS, [])
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_LINE_IDS,
                    default=current_line_ids,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=line_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }),
            errors=errors,
        )