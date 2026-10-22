# Live check that the TPER services still answer the way the integration expects

import asyncio
import sys
import time
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.tper_tracker.api import (
    HelloBusClient,
    TperApiError,
    TperNotServedError,
)
from custom_components.tper_tracker.stops import (
    async_download_stops_csv,
    async_latest_version,
    parse_stops_csv,
)

# Irnerio, a central stop served by several lines all day
DEFAULT_STOP = "303"
MIN_STOPS = 5000
MAX_LINES_CHECKED = 4


# Check the stop directory and Hello Bus, returning the exit code
async def main(stop_id: str) -> int:
    failures: list[str] = []

    async with aiohttp.ClientSession() as session:
        # Check the open-data portal still publishes the stop dataset in the same format
        started = time.monotonic()
        try:
            version = await async_latest_version(session)
            stops = parse_stops_csv(await async_download_stops_csv(session, version))
        except TperApiError as err:
            failures.append(f"open-data portal: {err}")
            stops = {}
        else:
            print(f"lineefermate {version}: {len(stops)} stops in {time.monotonic() - started:.1f}s")
        if len(stops) < MIN_STOPS:
            failures.append(f"only {len(stops)} stops in lineefermate, expected at least {MIN_STOPS}")

        stop = stops.get(stop_id)
        if stop is None or not stop.lines:
            failures.append(f"stop {stop_id} missing from lineefermate or has no lines")
            lines: tuple[str, ...] = ()
        else:
            print(f"stop {stop.label}: lines {', '.join(stop.lines)}")
            lines = stop.lines[:MAX_LINES_CHECKED]

        # Check every Hello Bus answer is one the parser understands
        client = HelloBusClient(session)
        for line in lines:
            try:
                arrivals = await client.async_get_arrivals(stop_id, line)
            except TperNotServedError as err:
                print(f"  line {line}: not served ({err})")
            except TperApiError as err:
                failures.append(f"Hello Bus line {line}: {type(err).__name__}: {err}")
            else:
                times = ", ".join(f"{a.time}{' GPS' if a.realtime else ''}" for a in arrivals) or "no buses"
                print(f"  line {line}: {times}")

    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    print("OK" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STOP)))
