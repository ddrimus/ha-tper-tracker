from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tper_tracker.const import OPEN_DATA_URL, STOPS_RETRY_DELAY
from custom_components.tper_tracker.stops import StopDirectory, parse_stops_csv

from .conftest import STOPS_CSV

DETAIL_URL = f"{OPEN_DATA_URL}/open-data-detail.aspx"
DOWNLOAD_URL = f"{OPEN_DATA_URL}/open-data-download.aspx"


# Register the open-data portal answers for version lookup and download
def mock_portal(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(DETAIL_URL, text='<a href="x?version=20260901">old</a> <a href="x?version=20261005">new</a>')
    aioclient_mock.get(DOWNLOAD_URL, text=STOPS_CSV)


# Test grouping lines by stop and formatting names
def test_parse_stops_csv() -> None:
    stops = parse_stops_csv(STOPS_CSV)
    assert stops["303"].name == "Irnerio"
    assert stops["303"].lines == ("20", "27", "N1")
    assert stops["1"].address == "Piazza Medaglie D'Oro (Pensilina C)"


# Test searching stops and loading the saved copy without downloading
async def test_search_and_storage(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_portal(aioclient_mock)
    directory = StopDirectory(hass)
    await directory.async_ensure_loaded()

    assert [stop.id for stop in directory.search("irnerio")] == ["303", "304"]
    assert [stop.id for stop in directory.search("via irnerio 18")] == ["304"]
    assert [stop.id for stop in directory.search("303")] == ["303"]
    assert [stop.id for stop in directory.search("medaglie d'oro")] == ["1"]
    assert directory.search("nowhere") == []
    assert aioclient_mock.mock_calls[-1][1].query["version"] == "20261005"

    # A second directory loads the saved copy without downloading again
    calls = aioclient_mock.call_count
    restored = StopDirectory(hass)
    await restored.async_ensure_loaded()
    assert aioclient_mock.call_count == calls
    assert restored.get("303").lines == ("20", "27", "N1")


# Test that an old saved copy is used at once and refreshed in the background
async def test_old_copy_refreshed_in_background(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_storage, freezer
) -> None:
    hass_storage["tper_tracker.stops"] = {
        "version": 1,
        "key": "tper_tracker.stops",
        "data": {"version": "20200101", "fetched": 0.0, "stops": [["999", "Old", "Via Old", "Bologna", ["1"]]]},
    }

    # A failing portal keeps the saved copy and is not asked again right away
    aioclient_mock.get(DETAIL_URL, exc=TimeoutError())
    directory = StopDirectory(hass)
    await directory.async_ensure_loaded()
    assert directory.get("999") is not None
    await hass.async_block_till_done(wait_background_tasks=True)
    assert directory.get("999") is not None
    calls = aioclient_mock.call_count
    await directory.async_ensure_loaded()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert aioclient_mock.call_count == calls

    # Try the portal again once the wait is over, and replace the saved copy
    aioclient_mock.clear_requests()
    mock_portal(aioclient_mock)
    freezer.tick(STOPS_RETRY_DELAY)
    await directory.async_ensure_loaded()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert directory.get("999") is None
    assert directory.get("303").lines == ("20", "27", "N1")
