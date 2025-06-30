from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    API_TIMEOUT,
    REAL_TIME_URL,
    STOP_LINES_URL,
    STOP_SEARCH_URL,
)

_LOGGER = logging.getLogger(__name__)


# Base exception class for TPER API errors
class TperApiError(Exception):
    pass


# Exception for when API returns no results
class TperApiNoResults(TperApiError):
    pass


# Exception for when real-time information is not available
class TperApiRealTimeNotAvailableError(TperApiError):
    pass


# Exception for when no more buses are scheduled
class TperApiNoMoreBusesError(TperApiError):
    pass


# Exception for TPER system errors
class TperApiSystemError(TperApiError):
    pass


# Rate limiter class to control API request frequency
class RateLimiter:
    def __init__(self, calls_per_second: float = 2.0) -> None:
        self._calls_per_second = calls_per_second
        self._min_interval = 1.0 / calls_per_second
        self._last_call_time = 0.0
        self._lock = asyncio.Lock()
    
    # Acquire rate limit permission before making API call
    async def acquire(self) -> None:
        async with self._lock:
            current_time = time.time()
            time_since_last_call = current_time - self._last_call_time
            
            if time_since_last_call < self._min_interval:
                sleep_time = self._min_interval - time_since_last_call
                await asyncio.sleep(sleep_time)
            
            self._last_call_time = time.time()


# Main API client class for interacting with TPER web services
class TperApiClient:
    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._rate_limiter = RateLimiter(calls_per_second=2.0)

    # Internal method to make HTTP requests to TPER API
    async def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._rate_limiter.acquire()
        
        # Add standard parameters required by TPER API
        params.update({
            "l": "it",
            "nocache": int(time.time() * 1000)
        })

        try:
            timeout = ClientTimeout(total=API_TIMEOUT)
            async with self._session.get(url, params=params, timeout=timeout) as response:
                response.raise_for_status()
                data = await response.json()
        except asyncio.TimeoutError as exc:
            raise TperApiError(f"Request timeout after {API_TIMEOUT} seconds") from exc
        except ClientError as exc:
            raise TperApiError(f"HTTP error: {exc}") from exc
        except Exception as exc:
            raise TperApiError(f"Unexpected error: {exc}") from exc

        # Handle API response errors and convert to specific exceptions
        if not data.get("successo"):
            if "risultati" in data and data["risultati"] and "Nessun risultato!" in data["risultati"][0].get("head", ""):
                raise TperApiNoResults("No results found")
            
            error_msg = data.get("errore", "")
            if "Informazioni in tempo reale non disponibili" in error_msg:
                raise TperApiRealTimeNotAvailableError(error_msg)
            if "prevista nessun'altra corsa" in error_msg:
                raise TperApiNoMoreBusesError(error_msg)
            if "qualche problema con il sistema di informazioni in tempo reale" in error_msg:
                raise TperApiSystemError(error_msg)

            raise TperApiError(error_msg or "Unknown API error")
            
        return data

    # Search for bus stops by query string
    async def async_search_stops(self, query: str) -> list[dict[str, Any]]:
        params = {"t": "fermate", "q": query}
        try:
            data = await self._request(STOP_SEARCH_URL, params)
            return data.get("risultati", [])
        except TperApiNoResults:
            return []

    # Get all bus lines for a specific stop
    async def async_get_stop_lines(self, stop_id: int) -> list[dict[str, Any]]:
        params = {"c": stop_id}
        data = await self._request(STOP_LINES_URL, params)
        return data.get("risultati", [])

    # Get real-time bus data for a specific stop and line
    async def async_get_real_time_data(self, stop_id: int, line_id: int) -> dict[str, Any]:
        params = {"t": "bus", "id": stop_id, "idL": line_id, "o": "null"}
        return await self._request(REAL_TIME_URL, params)
    
    # Get real-time data for multiple lines concurrently
    async def async_get_multiple_real_time_data(
        self, 
        stop_id: int, 
        line_ids: list[int], 
        max_concurrent: int = 3
    ) -> dict[str, dict[str, Any]]:
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # Helper function to fetch data for a single line with concurrency control
        async def get_line_data(line_id: int) -> tuple[str, dict[str, Any]]:
            async with semaphore:
                try:
                    data = await self.async_get_real_time_data(stop_id, line_id)
                    return str(line_id), data
                except Exception as exc:
                    return str(line_id), {"error": str(exc)}
        
        # Execute all requests concurrently and gather results
        tasks = [get_line_data(line_id) for line_id in line_ids]
        results = await asyncio.gather(*tasks)
        
        return dict(results)