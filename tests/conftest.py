from collections import Counter
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.tper_tracker.const import HELLOBUS_URL

STOPS_CSV = (
    "codice_linea;codice_fermata;denominazione;ubicazione;comune;coordinata_x;coordinata_y;"
    "latitudine;longitudine;codice_zona\r\n"
    "27;303;IRNERIO;VIA IRNERIO FR 20/C;BOLOGNA;686889;930270;44,499793;11,34979;500\r\n"
    "N1;303;IRNERIO;VIA IRNERIO FR 20/C;BOLOGNA;686889;930270;44,499793;11,34979;500\r\n"
    "20;303;IRNERIO;VIA IRNERIO FR 20/C;BOLOGNA;686889;930270;44,499793;11,34979;500\r\n"
    "27;304;IRNERIO;VIA IRNERIO 18;BOLOGNA;686900;930280;44,4999;11,3499;500\r\n"
    "14;304;IRNERIO;VIA IRNERIO 18;BOLOGNA;686900;930280;44,4999;11,3499;500\r\n"
    "1;1;STAZIONE CENTRALE;PIAZZA MEDAGLIE D`ORO (PENSILINA C);BOLOGNA;686344;930918;"
    "44,505762;11,343174;500\r\n"
)


# Wrap a Hello Bus answer in the XML envelope sent by TPER
def hellobus_xml(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\r\n'
        f'<string xmlns="https://hellobuswsweb.tper.it/web-services/hellobus.asmx">{body}</string>'
    )


# Allow Home Assistant to load the integration in every test
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


# Remove the delay between Hello Bus requests so tests run fast
@pytest.fixture(autouse=True)
def no_request_spacing():
    with patch("custom_components.tper_tracker.api.REQUEST_SPACING", 0):
        yield


NO_MORE = "TperHellobus: OGGI NESSUNA ALTRA CORSA DI {line} PER FERMATA {stop}"


# Fake Hello Bus whose answers per line can be changed while a test runs
class FakeHelloBus:
    # Initialize fake with no answers and register it for Hello Bus requests
    def __init__(self, aioclient_mock: AiohttpClientMocker) -> None:
        self.answers: dict[str, str] = {}
        self.calls: Counter[str] = Counter()
        self.stops: Counter[str] = Counter()
        aioclient_mock.get(HELLOBUS_URL, side_effect=self._answer)

    # Answer one request with the configured text for its line
    async def _answer(self, method, url, data):
        stop, line = url.query["fermata"], url.query["linea"]
        self.calls[line] += 1
        self.stops[stop] += 1
        body = self.answers.get(line, NO_MORE.format(line=line, stop=stop))
        return AiohttpClientMockResponse(method, url, text=hellobus_xml(body))
