from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store

from .api import TperApiError
from .const import (
    DATASET_TIMEOUT,
    DOMAIN,
    OPEN_DATA_URL,
    STOPS_DATASET,
    STOPS_MAX_AGE,
    STOPS_RETRY_DELAY,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
_VERSION_RE = re.compile(r"version=(\d{8})")


# A bus stop and the lines that serve it
@dataclass(frozen=True)
class Stop:
    id: str
    name: str
    address: str
    town: str
    lines: tuple[str, ...]

    # Label shown in the stop selection dropdown
    @property
    def label(self) -> str:
        return f"{self.name} - {self.address}, {self.town} ({self.id})"


# Lowercase and strip accents so searches ignore case and diacritics
def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("`", "'"))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


# TPER publishes names in upper case, with a backtick for the apostrophe
def _title(text: str) -> str:
    return text.strip().replace("`", "'").title()


# Sort lines numerically first (2, 13, 27), then alphabetically (N1, T2)
def _line_sort_key(line: str) -> tuple[int, int, str]:
    match = re.match(r"(\d+)(.*)", line)
    return (0, int(match.group(1)), match.group(2)) if match else (1, 0, line)


# Parse the lineefermate CSV (one row per line and stop) into stops
def parse_stops_csv(text: str) -> dict[str, Stop]:
    rows: dict[str, dict[str, Any]] = {}
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        stop_id = (row.get("codice_fermata") or "").strip()
        line = (row.get("codice_linea") or "").strip().upper()
        if not stop_id or not line:
            continue
        stop = rows.setdefault(
            stop_id,
            {
                "name": _title(row.get("denominazione") or ""),
                "address": _title(row.get("ubicazione") or ""),
                "town": _title(row.get("comune") or ""),
                "lines": set(),
            },
        )
        stop["lines"].add(line)

    return {
        stop_id: Stop(
            id=stop_id,
            name=stop["name"],
            address=stop["address"],
            town=stop["town"],
            lines=tuple(sorted(stop["lines"], key=_line_sort_key)),
        )
        for stop_id, stop in rows.items()
    }


# Internal function to make HTTP requests to the open-data portal
async def _async_get(session: ClientSession, url: str, params: dict[str, str]) -> bytes:
    try:
        async with session.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=ClientTimeout(total=DATASET_TIMEOUT),
        ) as response:
            response.raise_for_status()
            return await response.read()
    except TimeoutError as exc:
        raise TperApiError(f"Request timeout after {DATASET_TIMEOUT} seconds") from exc
    except ClientError as exc:
        raise TperApiError(f"HTTP error: {exc}") from exc


# Find the newest published version of the dataset on the open-data portal
async def async_latest_version(session: ClientSession) -> str:
    url = f"{OPEN_DATA_URL}/open-data-detail.aspx"
    content = await _async_get(session, url, {"filename": STOPS_DATASET})
    versions = _VERSION_RE.findall(content.decode("utf-8", errors="replace"))
    if not versions:
        raise TperApiError(f"No version of {STOPS_DATASET} found on the TPER portal")
    return max(versions)


# Download one version of the dataset as CSV text
async def async_download_stops_csv(session: ClientSession, version: str) -> str:
    url = f"{OPEN_DATA_URL}/open-data-download.aspx"
    params = {
        "source": "solweb.tper.it",
        "filename": STOPS_DATASET,
        "version": version,
        "format": "csv",
    }
    content = await _async_get(session, url, params)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    if "codice_fermata" not in text[:500]:
        raise TperApiError(f"TPER {STOPS_DATASET} download is not the expected CSV")
    return text


# Directory of TPER stops, downloaded from the open-data portal and saved in .storage
class StopDirectory:
    # Initialize directory with an empty index and its storage
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.stops")
        self._lock = asyncio.Lock()
        self._loaded = False
        self._stops: dict[str, Stop] = {}
        self._index: dict[str, str] = {}
        self._version: str | None = None
        self._fetched = 0.0
        self._retry_after = 0.0
        self._refresh_task: asyncio.Task[None] | None = None

    # Load the saved copy, downloading it when missing and refreshing an old one in the background
    async def async_ensure_loaded(self) -> None:
        async with self._lock:
            if not self._loaded:
                self._loaded = True
                if data := await self._store.async_load():
                    self._restore(data)

            if not self._stops:
                await self._async_refresh()
                return

        # Use the saved copy right away, so flows never wait for the portal
        now = time.time()
        refreshing = self._refresh_task is not None and not self._refresh_task.done()
        if not refreshing and now - self._fetched >= STOPS_MAX_AGE and now >= self._retry_after:
            self._refresh_task = self._hass.async_create_background_task(
                self._async_background_refresh(), f"{DOMAIN} stop list refresh"
            )

    # Refresh an old saved copy, waiting before the next try when the portal fails
    async def _async_background_refresh(self) -> None:
        try:
            async with self._lock:
                await self._async_refresh()
        except TperApiError as err:
            self._retry_after = time.time() + STOPS_RETRY_DELAY
            _LOGGER.warning("Could not refresh the TPER stop list, using the saved copy: %s", err)

    # Get a stop by its TPER code
    def get(self, stop_id: str) -> Stop | None:
        return self._stops.get(stop_id)

    # Search stops by code, name, address or town
    def search(self, query: str, limit: int = 50) -> list[Stop]:
        query = query.strip()
        tokens = _normalize(query).split()
        if not tokens:
            return []

        results: list[tuple[int, str, Stop]] = []
        for stop_id, haystack in self._index.items():
            if not all(token in haystack for token in tokens):
                continue
            stop = self._stops[stop_id]
            name = _normalize(stop.name)
            if stop_id == query:
                score = 0
            elif name.startswith(" ".join(tokens)):
                score = 1
            elif all(token in name for token in tokens):
                score = 2
            else:
                score = 3
            results.append((score, stop.name, stop))

        results.sort(key=lambda result: (result[0], result[1], result[2].id))
        return [stop for _, _, stop in results[:limit]]

    # Download the latest dataset unless the saved copy is already that version
    async def _async_refresh(self) -> None:
        session = async_get_clientsession(self._hass)
        version = await async_latest_version(session)

        if version != self._version or not self._stops:
            _LOGGER.debug("Downloading TPER %s version %s", STOPS_DATASET, version)
            text = await async_download_stops_csv(session, version)
            stops = await self._hass.async_add_executor_job(parse_stops_csv, text)
            if not stops:
                raise TperApiError(f"TPER {STOPS_DATASET} dataset is empty")
            self._set_stops(stops)
            self._version = version

        self._fetched = time.time()
        await self._store.async_save(self._serialize())

    # Replace the stops and rebuild the search index
    def _set_stops(self, stops: dict[str, Stop]) -> None:
        self._stops = stops
        self._index = {
            stop.id: _normalize(f"{stop.id} {stop.name} {stop.address} {stop.town}")
            for stop in stops.values()
        }

    # Convert the directory to the compact format saved in .storage
    def _serialize(self) -> dict[str, Any]:
        return {
            "version": self._version,
            "fetched": self._fetched,
            "stops": [
                [stop.id, stop.name, stop.address, stop.town, list(stop.lines)]
                for stop in self._stops.values()
            ],
        }

    # Restore the directory from the saved copy
    def _restore(self, data: dict[str, Any]) -> None:
        try:
            stops = {
                stop_id: Stop(stop_id, name, address, town, tuple(lines))
                for stop_id, name, address, town, lines in data["stops"]
            }
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning("Ignoring an invalid saved TPER stop list")
            return
        self._set_stops(stops)
        self._version = data.get("version")
        self._fetched = data.get("fetched", 0.0)


# One stop directory per Home Assistant instance
@singleton(f"{DOMAIN}_stops")
@callback
def async_get_stop_directory(hass: HomeAssistant) -> StopDirectory:
    return StopDirectory(hass)
