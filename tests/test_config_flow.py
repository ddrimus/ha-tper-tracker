from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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


# Test the full setup flow from search to entry creation
async def test_user_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_portal(aioclient_mock)
    aioclient_mock.get(HELLOBUS_URL, text=hellobus_xml("TperHellobus: OGGI NESSUNA ALTRA CORSA"))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "   "})
    assert result["errors"] == {"stop_query": "invalid_query"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "nowhere"})
    assert result["errors"] == {"base": "no_stops_found"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "irnerio"})
    assert result["step_id"] == "select_stop"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STOP_ID: "303"})
    assert result["step_id"] == "select_lines"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LINES: []})
    assert result["errors"] == {CONF_LINES: "invalid_line_selection"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LINES: ["27", "N1"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Irnerio (303)"
    assert result["data"] == {CONF_STOP_ID: "303", "stop_name": "Irnerio"}
    assert result["options"] == {CONF_LINES: ["27", "N1"]}
    assert result["result"].unique_id == "303"


# Test the error shown when the stop list cannot be downloaded
async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get("https://solweb.tper.it/web/tools/open-data/open-data-detail.aspx", status=500)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "irnerio"})
    assert result["errors"] == {"base": "cannot_connect"}


# Test adding a line from the options flow
async def test_options_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_portal(aioclient_mock)
    aioclient_mock.get(HELLOBUS_URL, text=hellobus_xml("TperHellobus: OGGI NESSUNA ALTRA CORSA"))
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, unique_id="303", title="Irnerio (303)",
        data={CONF_STOP_ID: "303", "stop_name": "Irnerio"}, options={CONF_LINES: ["27"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_LINES: ["20", "27"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_LINES: ["20", "27"]}
    assert hass.states.get("sensor.tper_tracker_303_line_20") is not None
