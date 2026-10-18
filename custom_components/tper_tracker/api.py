from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from dataclasses import dataclass

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import API_TIMEOUT, HELLOBUS_URL, LOCK_BACKOFF, REQUEST_SPACING, USER_AGENT

_LOGGER = logging.getLogger(__name__)

# Pattern for one arrival in a Hello Bus answer, such as 27A DaSatellite 12:00 (Bus5593 CON PEDANA)
_ENTRY_RE = re.compile(
    r"^\s*([A-Z0-9]+)\s+(\S+)\s+(\d{1,2}):(\d{2})(?:\s*\(([^)]*)\))?", re.IGNORECASE
)
_BODY_RE = re.compile(r"<string[^>]*>(.*?)</string>", re.DOTALL)
_VEHICLE_RE = re.compile(r"Bus\s*(\d+)", re.IGNORECASE)


# Base exception class for TPER API errors
class TperApiError(Exception):
    pass


# Exception for when TPER has locked this IP for sending too many requests
class TperRateLimitedError(TperApiError):
    pass


# Exception for when Hello Bus does not know the requested stop or line
class TperNotServedError(TperApiError):
    pass


# A single predicted arrival at a stop
@dataclass(frozen=True)
class Arrival:
    line: str
    time: str
    realtime: bool
    vehicle: str | None
    accessible: bool | None


# Check whether a Hello Bus line (27A) belongs to a configured line (27)
def line_matches(reported: str, line: str) -> bool:
    reported, line = reported.upper(), line.upper()
    if reported == line:
        return True
    suffix = reported[len(line):]
    return reported.startswith(line) and len(suffix) == 1 and suffix.isalpha()


# Parse a Hello Bus XML answer into the arrivals for one line
def parse_hellobus(text: str, line: str) -> list[Arrival]:
    match = _BODY_RE.search(text)
    body = html.unescape(match.group(1) if match else text).strip()

    if body.upper().startswith("ERR_"):
        if "TOO_MANY" in body.upper() or "LOCK" in body.upper():
            raise TperRateLimitedError(body)
        raise TperApiError(body)
    if body.startswith("HellobusHelp:"):
        raise TperNotServedError(body.split(",")[0].removeprefix("HellobusHelp:").strip())
    if not body.startswith("TperHellobus:"):
        raise TperApiError(f"Unexpected response: {body[:100]}")

    payload = body.removeprefix("TperHellobus:").strip()
    if "NESSUNA ALTRA CORSA" in payload.upper():
        return []

    arrivals = []
    for part in payload.split(","):
        entry = _ENTRY_RE.match(part)
        if not entry or not line_matches(entry.group(1), line):
            continue
        details = (entry.group(5) or "").upper()
        vehicle = _VEHICLE_RE.search(details)
        arrivals.append(
            Arrival(
                line=entry.group(1).upper(),
                time=f"{int(entry.group(3)):02d}:{entry.group(4)}",
                realtime="SATELLITE" in entry.group(2).upper(),
                vehicle=vehicle.group(1) if vehicle else None,
                accessible=(
                    True if "CON PEDANA" in details
                    else False if "SENZA PEDANA" in details
                    else None
                ),
            )
        )
    return arrivals


# Client for TPER Hello Bus, shared by all config entries so the rate limit is global
class HelloBusClient:
    # Initialize client with the shared HTTP session
    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._paused_until = 0.0
        self.stats = {"requests": 0, "errors": 0, "rate_limited": 0}

    # Seconds left before requests resume after a TPER rate limit
    @property
    def paused_for(self) -> float:
        return max(0.0, self._paused_until - time.monotonic())

    # Get the next arrivals of one line at one stop
    async def async_get_arrivals(self, stop_id: str, line: str) -> list[Arrival]:
        async with self._lock:
            if time.monotonic() < self._paused_until:
                raise TperRateLimitedError("Hello Bus paused after a TPER rate limit")

            wait = self._last_request + REQUEST_SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

            self.stats["requests"] += 1
            try:
                return parse_hellobus(await self._request(stop_id, line), line)
            except TperRateLimitedError:
                self.stats["rate_limited"] += 1
                self._paused_until = time.monotonic() + LOCK_BACKOFF
                _LOGGER.warning(
                    "TPER rate limit reached, pausing Hello Bus requests for %d minutes",
                    LOCK_BACKOFF // 60,
                )
                raise
            except TperNotServedError:
                raise
            except TperApiError:
                self.stats["errors"] += 1
                raise

    # Internal method to make the HTTP request to Hello Bus
    async def _request(self, stop_id: str, line: str) -> str:
        params = {"fermata": stop_id, "linea": line, "oraHHMM": ""}
        try:
            async with self._session.get(
                HELLOBUS_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=ClientTimeout(total=API_TIMEOUT),
            ) as response:
                if response.status == 429:
                    raise TperRateLimitedError("HTTP 429")
                response.raise_for_status()
                return await response.text()
        except TimeoutError as exc:
            raise TperApiError(f"Request timeout after {API_TIMEOUT} seconds") from exc
        except ClientError as exc:
            raise TperApiError(f"HTTP error: {exc}") from exc
