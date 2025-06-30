from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .coordinator import TperDataUpdateCoordinator
from .const import CONF_LINE_IDS, CONF_LINE_NAMES, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Define supported platforms for this integration
PLATFORMS: list[Platform] = [Platform.SENSOR]


# Main entry point for setting up the TPER Tracker integration
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Setting up TPER Tracker entry %s", entry.entry_id)
    
    # Migrate configuration from data to options if needed (for backward compatibility)
    if not entry.options and CONF_LINE_IDS in entry.data:
        _LOGGER.info("Migrating configuration from data to options for entry %s", entry.entry_id)
        options = {
            CONF_LINE_IDS: entry.data[CONF_LINE_IDS],
            CONF_LINE_NAMES: entry.data.get(CONF_LINE_NAMES, {}),
        }
        
        new_data = {
            key: value for key, value in entry.data.items()
            if key not in (CONF_LINE_IDS, CONF_LINE_NAMES)
        }
        
        hass.config_entries.async_update_entry(
            entry, 
            data=new_data, 
            options=options
        )

    # Initialize the data coordinator and perform first refresh
    try:
        coordinator = TperDataUpdateCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error("Failed to initialize coordinator for entry %s: %s", entry.entry_id, err)
        return False

    # Store coordinator in hass data for access by platforms
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    
    # Set up all platforms (sensors) for this integration
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception as err:
        _LOGGER.error("Failed to setup platforms for entry %s: %s", entry.entry_id, err)
        return False
    
    # Register reload listener for configuration changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _LOGGER.info("TPER Tracker entry %s setup completed successfully", entry.entry_id)
    
    return True


# Function to unload the integration entry
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading TPER Tracker entry %s", entry.entry_id)
    
    try:
        # Unload all platforms and clean up data
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            hass.data[DOMAIN].pop(entry.entry_id)
            _LOGGER.info("TPER Tracker entry %s unloaded successfully", entry.entry_id)
        return unload_ok
    except Exception as err:
        _LOGGER.error("Error during unload of entry %s: %s", entry.entry_id, err)
        return False


# Function to reload the integration entry when configuration changes
async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.info("Reloading TPER Tracker entry %s", entry.entry_id)
    try:
        await hass.config_entries.async_reload(entry.entry_id)
    except Exception as err:
        _LOGGER.error("Failed to reload entry %s: %s", entry.entry_id, err)