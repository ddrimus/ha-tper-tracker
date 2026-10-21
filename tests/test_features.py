from homeassistant import config_entries
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tper_tracker.const import CONF_ACTIVE_ENTITY, CONF_LINES, CONF_STOP_ID, DOMAIN

from .conftest import FakeHelloBus
from .test_stops import mock_portal

NOT_SERVED = "HellobusHelp: LINEA {line} NON GESTITA, indicare FERMATA LINEA"
ARRIVING = "TperHellobus: 27A DaSatellite 13:48 (Bus5662 CON PEDANA)"


# Create a config entry for a stop with the given lines and options
def make_entry(stop_id: str = "303", lines: list[str] | None = None, **options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, version=2, unique_id=stop_id, title=f"Irnerio ({stop_id})",
        data={CONF_STOP_ID: stop_id, "stop_name": "Irnerio"},
        options={CONF_LINES: lines or ["27"], **options},
    )


# Add the entry and set it up, waiting for the background stop check
async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


# Test reconfigure moving the device and preselecting lines served at both stops
async def test_reconfigure_moves_device_and_preselects_lines(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, device_registry: dr.DeviceRegistry
) -> None:
    mock_portal(aioclient_mock)
    hellobus = FakeHelloBus(aioclient_mock)
    entry = make_entry(lines=["20", "27"])
    await setup(hass, entry)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "via irnerio 18"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STOP_ID: "304"})
    assert result["step_id"] == "select_lines"
    # Line 27 is served at both stops so it is preselected, while 20 is not served at 304
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults[CONF_LINES] == ["27"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_LINES: ["14", "27"]})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert entry.title == "Irnerio (304)"
    assert entry.data[CONF_STOP_ID] == "304"
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert [(device.identifiers, device.name) for device in devices] == [
        ({(DOMAIN, "304")}, "TPER Tracker #304")
    ]
    assert hass.states.get("sensor.tper_tracker_303_line_27") is not None
    assert hass.states.get("sensor.tper_tracker_304_line_14") is not None
    # The entry is set up once at the new stop, asking each line a single time
    assert hellobus.stops["304"] == 2


# Test that reconfigure refuses a stop already tracked by another entry
async def test_reconfigure_to_another_entrys_stop_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_portal(aioclient_mock)
    FakeHelloBus(aioclient_mock)
    entry = make_entry("303")
    await setup(hass, entry)
    make_entry("304").add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "irnerio"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STOP_ID: "304"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == "303"


# Test that no request is sent when starting outside active hours
async def test_inactive_at_startup_sends_no_requests(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    assert await async_setup_component(hass, "input_boolean", {"input_boolean": {"commute": {"initial": False}}})
    mock_portal(aioclient_mock)
    hellobus = FakeHelloBus(aioclient_mock)
    hellobus.answers["27"] = ARRIVING
    entry = make_entry(**{CONF_ACTIVE_ENTITY: "input_boolean.commute"})
    await setup(hass, entry)

    state = hass.states.get("sensor.tper_tracker_303_line_27")
    assert state.state == "unknown"
    assert state.attributes["status"] == "inactive"
    assert hellobus.calls["27"] == 0
    assert entry.runtime_data.update_interval is None


# Test that a missing active entity keeps polling and raises an issue
async def test_missing_active_entity_keeps_polling_and_raises_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, issue_registry: ir.IssueRegistry
) -> None:
    mock_portal(aioclient_mock)
    hellobus = FakeHelloBus(aioclient_mock)
    hellobus.answers["27"] = ARRIVING
    entry = make_entry(**{CONF_ACTIVE_ENTITY: "schedule.deleted"})
    await setup(hass, entry)

    assert hass.states.get("sensor.tper_tracker_303_line_27").attributes["status"] == "ok"
    issue = issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_active_entity_missing")
    assert issue.translation_placeholders["entity_id"] == "schedule.deleted"

    # Clearing the option resolves the issue
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_LINES: ["27"]})
    await hass.async_block_till_done()
    assert CONF_ACTIVE_ENTITY not in entry.options
    assert issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_active_entity_missing") is None


# Test the issue raised when the stop is no longer in the TPER stop list
async def test_stop_removed_from_tper_raises_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, issue_registry: ir.IssueRegistry
) -> None:
    mock_portal(aioclient_mock)
    FakeHelloBus(aioclient_mock)
    entry = make_entry("999")
    await setup(hass, entry)

    issue = issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_stop_not_found")
    assert issue is not None
    assert not issue.is_fixable

    assert await hass.config_entries.async_remove(entry.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_stop_not_found") is None


# Test that no issue is raised when the stop list cannot be downloaded
async def test_no_issue_when_stop_list_unreachable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, issue_registry: ir.IssueRegistry
) -> None:
    aioclient_mock.get("https://solweb.tper.it/web/tools/open-data/open-data-detail.aspx", status=503)
    FakeHelloBus(aioclient_mock)
    entry = make_entry("999")
    await setup(hass, entry)
    assert any("open-data-detail" in str(call[1]) for call in aioclient_mock.mock_calls)
    assert issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_stop_not_found") is None


# Test the fix flow that stops tracking lines not served
async def test_lines_not_served_fix_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    issue_registry: ir.IssueRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    assert await async_setup_component(hass, "repairs", {})
    mock_portal(aioclient_mock)
    hellobus = FakeHelloBus(aioclient_mock)
    hellobus.answers["27"] = ARRIVING
    hellobus.answers["N1"] = NOT_SERVED.format(line="N1")
    entry = make_entry(lines=["27", "N1"])
    await setup(hass, entry)
    issue_id = f"{entry.entry_id}_lines_not_served"
    assert issue_registry.async_get_issue(DOMAIN, issue_id).is_fixable

    manager = repairs_flow_manager(hass)
    result = await manager.async_init(DOMAIN, data={"issue_id": issue_id})
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["lines"] == "N1"
    result = await manager.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options[CONF_LINES] == ["27"]
    assert entity_registry.async_get("sensor.tper_tracker_303_line_n1") is None
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


# Test that the issue is not fixable when no served line would remain
async def test_lines_not_served_not_fixable_when_none_left(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, issue_registry: ir.IssueRegistry
) -> None:
    mock_portal(aioclient_mock)
    hellobus = FakeHelloBus(aioclient_mock)
    hellobus.answers["27"] = NOT_SERVED.format(line="27")
    entry = make_entry()
    await setup(hass, entry)
    issue = issue_registry.async_get_issue(DOMAIN, f"{entry.entry_id}_lines_not_served")
    assert not issue.is_fixable
    assert issue.translation_key == "no_lines_served"


# Test that setup still refuses a stop that is already configured
async def test_user_flow_still_aborts_on_configured_stop(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_portal(aioclient_mock)
    FakeHelloBus(aioclient_mock)
    await setup(hass, make_entry("303"))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_query": "irnerio"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_STOP_ID: "303"})
    assert result["reason"] == "already_configured"
