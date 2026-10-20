from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.singleton import singleton

from .api import HelloBusClient, TperApiError
from .const import CONF_STOP_ID, DOMAIN, STOP_CHECK_INTERVAL
from .coordinator import TperConfigEntry, TperDataUpdateCoordinator
from .issues import ISSUE_STOP_NOT_FOUND, async_delete_issues, async_set_issue
from .stops import async_get_stop_directory

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

    # Check in the background that the stop still exists, at startup and then daily
    @callback
    def _async_schedule_stop_check(_now: datetime | None = None) -> None:
        entry.async_create_background_task(hass, _async_check_stop(hass, entry), f"{DOMAIN} stop check")

    _async_schedule_stop_check()
    entry.async_on_unload(
        async_track_time_interval(hass, _async_schedule_stop_check, timedelta(seconds=STOP_CHECK_INTERVAL))
    )

    # Register reload listener for configuration changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


# Raise a repair issue when the configured stop is no longer in the TPER stop list
async def _async_check_stop(hass: HomeAssistant, entry: TperConfigEntry) -> None:
    directory = async_get_stop_directory(hass)
    try:
        await directory.async_ensure_loaded()
    except TperApiError as err:
        _LOGGER.debug("Could not check stop %s against the TPER stop list: %s", entry.data[CONF_STOP_ID], err)
        return
    async_set_issue(hass, entry, ISSUE_STOP_NOT_FOUND, directory.get(entry.data[CONF_STOP_ID]) is None)


# Function to unload the integration entry
async def async_unload_entry(hass: HomeAssistant, entry: TperConfigEntry) -> bool:
    _LOGGER.debug("Unloading TPER Tracker entry %s", entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


# Function to clean up repair issues when the integration entry is deleted
async def async_remove_entry(hass: HomeAssistant, entry: TperConfigEntry) -> None:
    async_delete_issues(hass, entry)


# Function to reload the integration entry when configuration changes
async def async_reload_entry(hass: HomeAssistant, entry: TperConfigEntry) -> None:
    _LOGGER.debug("Reloading TPER Tracker entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
