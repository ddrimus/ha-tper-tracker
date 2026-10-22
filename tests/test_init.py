from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tper_tracker.const import (
    CONF_LINES,
    CONF_STOP_ID,
    DOMAIN,
    HELLOBUS_URL,
)

from .conftest import hellobus_xml
from .test_stops import mock_portal


# Create a config entry for stop 303 with the given lines
def make_entry(lines: list[str]) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, version=2, unique_id="303", title="Irnerio (303)",
        data={CONF_STOP_ID: "303", "stop_name": "Irnerio"}, options={CONF_LINES: lines},
    )


# Register the Hello Bus answer for one line at stop 303
def mock_line(aioclient_mock: AiohttpClientMocker, line: str, body: str) -> None:
    aioclient_mock.get(
        HELLOBUS_URL,
        params={"fermata": "303", "linea": line, "oraHHMM": ""},
        text=hellobus_xml(body),
    )


# Test sensor states and attributes for served, ended and unserved lines
async def test_sensor_state(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer) -> None:
    mock_portal(aioclient_mock)
    freezer.move_to("2026-10-22 13:40:00+02:00")
    mock_line(
        aioclient_mock,
        "27",
        "TperHellobus: 27A DaSatellite 13:48 (Bus5662 CON PEDANA), 27B DaOrario 14:05 (SENZA PEDANA)",
    )
    mock_line(aioclient_mock, "N1", "TperHellobus: OGGI NESSUNA ALTRA CORSA DI N1 PER FERMATA 303")
    mock_line(aioclient_mock, "99", "HellobusHelp: LINEA 99 NON GESTITA, indicare FERMATA LINEA")

    entry = make_entry(["27", "N1", "99"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.tper_tracker_303_line_27")
    assert state.state == "2026-10-22T11:48:00+00:00"
    assert state.attributes["device_class"] == "timestamp"
    assert state.attributes["status"] == "ok"
    assert state.attributes["next_bus_1_satellite"] is True
    assert state.attributes["next_bus_1_vehicle"] == "5662"
    assert state.attributes["next_bus_2_time"] == "14:05"
    assert state.attributes["next_bus_2_accessible"] is False

    state = hass.states.get("sensor.tper_tracker_303_line_n1")
    assert state.state == "unknown"
    assert state.attributes["status"] == "no_buses"
    assert hass.states.get("sensor.tper_tracker_303_line_99").attributes["status"] == "not_served"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


# Test that a TPER lock pauses all requests and retries setup later
async def test_rate_limit_pauses_requests(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_portal(aioclient_mock)
    mock_line(aioclient_mock, "27", "ERR_TOO_MANY_REQUESTS_LOCK")
    entry = make_entry(["27"])
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY

    # While paused, retries do not contact TPER at all
    calls = aioclient_mock.call_count
    await hass.config_entries.async_reload(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert aioclient_mock.call_count == calls


# Test that a bus whose time just passed keeps the fast polling
async def test_late_bus_keeps_fast_polling(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer) -> None:
    mock_portal(aioclient_mock)
    freezer.move_to("2026-10-22 13:40:00+02:00")
    mock_line(aioclient_mock, "27", "TperHellobus: 27A DaSatellite 13:38 (Bus5662 CON PEDANA)")
    entry = make_entry(["27"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.update_interval == timedelta(seconds=30)


# Test that an unexpected answer for one line does not hide the other lines
async def test_unexpected_answer_marks_only_that_line(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_portal(aioclient_mock)
    mock_line(aioclient_mock, "27", "TperHellobus: 27A DaSatellite 13:48 (Bus5662 CON PEDANA)")
    mock_line(aioclient_mock, "N1", "SOMETHING NEW")
    entry = make_entry(["27", "N1"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.tper_tracker_303_line_27").attributes["status"] == "ok"
    assert hass.states.get("sensor.tper_tracker_303_line_n1").attributes["status"] == "error"
