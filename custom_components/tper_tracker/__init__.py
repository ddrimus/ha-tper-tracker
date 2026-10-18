from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.singleton import singleton

from .api import HelloBusClient
from .const import DOMAIN
from .coordinator import TperConfigEntry, TperDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Define supported platforms for this integration
PLATFORMS: list[Platform] = [Platform.SENSOR]


# One Hello Bus client per Home Assistant instance, so the TPER rate limit is shared
@singleton(f"{DOMAIN}_hellobus")
@callback
def async_get_hellobus_client(hass: HomeAssistant) -> HelloBusClient:
    return HelloBusClient(async_get_clientsession(hass))


# Main entry point for setting up the TPER Tracker integration
async def async_setup_entry(hass: HomeAssistant, entry: TperConfigEntry) -> bool:
    _LOGGER.debug("Setting up TPER Tracker entry %s", entry.entry_id)

    # Initialize the data coordinator and perform first refresh
    coordinator = TperDataUpdateCoordinator(hass, entry, async_get_hellobus_client(hass))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Set up all platforms (sensors) for this integration
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register reload listener for configuration changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


# Function to unload the integration entry
async def async_unload_entry(hass: HomeAssistant, entry: TperConfigEntry) -> bool:
    _LOGGER.debug("Unloading TPER Tracker entry %s", entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


# Function to reload the integration entry when configuration changes
async def async_reload_entry(hass: HomeAssistant, entry: TperConfigEntry) -> None:
    _LOGGER.debug("Reloading TPER Tracker entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
