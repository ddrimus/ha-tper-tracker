# End-to-end check of every component working together, from setup to removal

import json
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.json import json_dumps
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tper_tracker.const import (
    CONF_ACTIVE_ENTITY,
    CONF_LINES,
    CONF_STOP_ID,
    DOMAIN,
    LOCK_BACKOFF,
)
from custom_components.tper_tracker.diagnostics import async_get_config_entry_diagnostics

from .conftest import NO_MORE, FakeHelloBus
from .test_stops import mock_portal

SENSOR_20 = "sensor.tper_tracker_303_line_20"
SENSOR_27 = "sensor.tper_tracker_303_line_27"
SENSOR_N1 = "sensor.tper_tracker_303_line_n1"
COMMUTE = "input_boolean.commute"


# Move time forward and run the timers that are due
async def _advance(hass: HomeAssistant, freezer, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


# Test one installation through its whole life with a fake Hello Bus
async def test_full_lifecycle(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_registry: er.EntityRegistry,
    issue_registry: ir.IssueRegistry,
    freezer,
) -> None:
    freezer.move_to("2026-10-22 13:40:00+02:00")
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"commute": {"initial": True}}})
    mock_portal(aioclient_mock)
    hellobus = FakeHelloBus(aioclient_mock)
    hellobus.answers["27"] = "TperHellobus: 27A DaSatellite 13:48 (Bus5662 CON PEDANA), 27B DaOrario 14:05"
    hellobus.answers["N1"] = "HellobusHelp: LINEA N1 NON GESTITA, indicare FERMATA LINEA"

    # Complete the config flow, which sets up the entry right away
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "via irnerio"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STOP_ID: "303"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LINES: ["20", "27", "N1"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    entry = result["result"]
    coordinator = entry.runtime_data
    assert entry.state is ConfigEntryState.LOADED

    # Check the first data of each line sensor
    state = hass.states.get(SENSOR_27)
    assert state.state == "2026-10-22T11:48:00+00:00"
    assert state.attributes["status"] == "ok"
    assert state.attributes["next_bus_1_vehicle"] == "5662"
    assert state.attributes["attribution"] == "Data provided by TPER (CC BY 3.0 IT)"
    assert hass.states.get(SENSOR_20).attributes["status"] == "no_buses"
    assert hass.states.get(SENSOR_N1).attributes["status"] == "not_served"
    assert coordinator.update_interval == timedelta(seconds=60)

    # Check the fixable issue for the unserved line, and no issue for the stop
    issue = issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_lines_not_served")
    assert issue.is_fixable
    assert issue.translation_placeholders["lines"] == "N1"
    assert issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_stop_not_found") is None

    # Speed up polling as the bus gets closer, without asking the unserved line again
    hellobus.answers["27"] = "TperHellobus: 27A DaSatellite 13:43 (Bus5662 CON PEDANA)"
    await _advance(hass, freezer, 60)
    assert hass.states.get(SENSOR_27).state == "2026-10-22T11:43:00+00:00"
    assert coordinator.update_interval == timedelta(seconds=30)
    assert hellobus.calls["N1"] == 1

    # Slow down polling to the idle interval when service ends
    hellobus.answers["27"] = NO_MORE.format(line="27", stop="303")
    await _advance(hass, freezer, 30)
    assert hass.states.get(SENSOR_27).state == "unknown"
    assert coordinator.update_interval == timedelta(seconds=300)

    # Make sensors unavailable and send no request while TPER locks the IP
    hellobus.answers["20"] = "ERR_TOO_MANY_REQUESTS_LOCK"
    await _advance(hass, freezer, 300)
    assert hass.states.get(SENSOR_27).state == STATE_UNAVAILABLE
    calls = sum(hellobus.calls.values())
    await _advance(hass, freezer, 300)
    assert sum(hellobus.calls.values()) == calls

    # Recover once the pause is over
    hellobus.answers["20"] = "TperHellobus: 20 DaSatellite 14:10 (Bus5593 CON PEDANA)"
    await _advance(hass, freezer, LOCK_BACKOFF)
    assert hass.states.get(SENSOR_20).attributes["status"] == "ok"
    assert hass.states.get(SENSOR_27).state == "unknown"

    # Check diagnostics are serializable, with counters and the stop redacted
    diagnostics = json.loads(json_dumps(await async_get_config_entry_diagnostics(hass, entry)))
    assert diagnostics["entry"]["data"][CONF_STOP_ID] == "**REDACTED**"
    assert diagnostics["entry"]["title"] == "**REDACTED**"
    assert diagnostics["hellobus"]["rate_limited"] == 1
    assert diagnostics["hellobus"]["paused_for"] == 0
    assert diagnostics["lines"]["20"]["arrivals"][0]["vehicle"] == "5593"

    # Drop the unserved line and track only during the commute
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_LINES: ["20", "27"], CONF_ACTIVE_ENTITY: COMMUTE}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entity_registry.async_get(SENSOR_N1) is None
    assert entity_registry.async_get(SENSOR_20) is not None
    assert issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_lines_not_served") is None
    coordinator = entry.runtime_data

    # Stop requests and polling outside active hours
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": COMMUTE}, blocking=True)
    await _advance(hass, freezer, 11)
    assert hass.states.get(SENSOR_20).attributes["status"] == "inactive"
    assert coordinator.update_interval is None
    calls = sum(hellobus.calls.values())
    await _advance(hass, freezer, 3600)
    assert sum(hellobus.calls.values()) == calls

    # Resume live data as soon as active hours start
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": COMMUTE}, blocking=True)
    await _advance(hass, freezer, 11)
    assert hass.states.get(SENSOR_20).attributes["status"] == "ok"
    assert coordinator.update_interval is not None

    # Reconfigure to the stop across the street, keeping line 27 and dropping 20
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "via irnerio 18"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STOP_ID: "304"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LINES: ["27"]})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.unique_id == "304"
    assert entity_registry.async_get(SENSOR_27).unique_id == "tper_tracker_304_27"
    assert entity_registry.async_get(SENSOR_20) is None
    assert entry.options[CONF_ACTIVE_ENTITY] == COMMUTE
    coordinator = entry.runtime_data

    # Date a bus after midnight tomorrow, asking the new stop
    freezer.move_to("2026-10-22 23:55:00+02:00")
    hellobus.answers["27"] = "TperHellobus: 27A DaSatellite 00:10 (Bus5662 CON PEDANA)"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR_27).state == "2026-10-22T22:10:00+00:00"
    assert hellobus.stops["304"] > 0

    # Remove the entry, cleaning up its entities and issues
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR_27) is None
    assert not er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert not [issue for issue in issue_registry.issues.values() if issue.domain == DOMAIN]
