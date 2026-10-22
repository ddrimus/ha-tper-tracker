import time
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tper_tracker.api import (
    HelloBusClient,
    TperApiError,
    TperNotServedError,
    TperRateLimitedError,
    line_matches,
    parse_hellobus,
)
from custom_components.tper_tracker.const import HELLOBUS_URL
from custom_components.tper_tracker.coordinator import resolve_arrival_time

from .conftest import hellobus_xml

ROME = ZoneInfo("Europe/Rome")


# Test parsing GPS and timetable arrivals with vehicle and accessibility
def test_parse_arrivals() -> None:
    arrivals = parse_hellobus(
        hellobus_xml(
            "TperHellobus: 27A DaSatellite 13:48 (Bus5662 CON PEDANA), "
            "27B DaOrario 9:05 (SENZA PEDANA)"
        ),
        "27",
    )
    assert [(a.line, a.time, a.realtime, a.vehicle, a.accessible) for a in arrivals] == [
        ("27A", "13:48", True, "5662", True),
        ("27B", "09:05", False, None, False),
    ]


# Test that buses of other lines in the answer are ignored
def test_parse_ignores_other_lines() -> None:
    # Hello Bus sometimes answers with buses of other lines
    arrivals = parse_hellobus(
        hellobus_xml("TperHellobus: 101 DaSatellite 13:51 (Bus1837 CON PEDANA), 14A DaSatellite 13:54"),
        "14",
    )
    assert [a.line for a in arrivals] == ["14A"]


# Test the answer sent when no more buses are scheduled today
def test_parse_no_more_buses() -> None:
    assert parse_hellobus(hellobus_xml("TperHellobus: OGGI NESSUNA ALTRA CORSA DI 27 PER FERMATA 303"), "27") == []


# Test that each Hello Bus error answer raises the right exception
@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("ERR_TOO_MANY_REQUESTS_LOCK", TperRateLimitedError),
        ("ERR_SOMETHING", TperApiError),
        ("HellobusHelp: LINEA 999 NON GESTITA, indicare FERMATA LINEA", TperNotServedError),
        ("FORBIDDEN", TperApiError),
    ],
)
def test_parse_errors(body: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        parse_hellobus(hellobus_xml(body), "27")


# Test matching Hello Bus line variants to configured lines
@pytest.mark.parametrize(
    ("reported", "line", "expected"),
    [("27", "27", True), ("27A", "27", True), ("270", "27", False), ("N1", "N1", True), ("2", "27", False)],
)
def test_line_matches(reported: str, line: str, expected: bool) -> None:
    assert line_matches(reported, line) is expected


# Test arrival times on the same day and across midnight in both directions
@pytest.mark.parametrize(
    ("now", "hhmm", "expected"),
    [
        (datetime(2026, 10, 22, 13, 40, tzinfo=ROME), "13:48", datetime(2026, 10, 22, 13, 48, tzinfo=ROME)),
        (datetime(2026, 10, 22, 13, 40, tzinfo=ROME), "13:38", datetime(2026, 10, 22, 13, 38, tzinfo=ROME)),
        (datetime(2026, 10, 22, 23, 55, tzinfo=ROME), "00:10", datetime(2026, 10, 23, 0, 10, tzinfo=ROME)),
        (datetime(2026, 10, 23, 0, 2, tzinfo=ROME), "23:58", datetime(2026, 10, 22, 23, 58, tzinfo=ROME)),
    ],
)
def test_resolve_arrival_time(now: datetime, hhmm: str, expected: datetime) -> None:
    assert resolve_arrival_time(hhmm, now) == expected


# Test that requests go out in a short burst, then wait for the spacing
async def test_request_burst_then_spacing(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(HELLOBUS_URL, text=hellobus_xml("TperHellobus: OGGI NESSUNA ALTRA CORSA"))
    with (
        patch("custom_components.tper_tracker.api.REQUEST_BURST", 3),
        patch("custom_components.tper_tracker.api.REQUEST_SPACING", 0.2),
    ):
        client = HelloBusClient(async_get_clientsession(hass))
        started = time.monotonic()
        for _ in range(3):
            await client.async_get_arrivals("303", "27")
        burst = time.monotonic() - started
        for _ in range(2):
            await client.async_get_arrivals("303", "27")
        total = time.monotonic() - started

    assert burst < 0.2
    assert total >= 0.38


# Test that HTTP 429 pauses requests like the Hello Bus lock answer
async def test_http_429_pauses_requests(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(HELLOBUS_URL, status=429)
    client = HelloBusClient(async_get_clientsession(hass))

    with pytest.raises(TperRateLimitedError):
        await client.async_get_arrivals("303", "27")
    assert client.paused_for > 0
    assert client.stats["rate_limited"] == 1

    # While paused, nothing is sent to TPER
    with pytest.raises(TperRateLimitedError):
        await client.async_get_arrivals("303", "27")
    assert aioclient_mock.call_count == 1
