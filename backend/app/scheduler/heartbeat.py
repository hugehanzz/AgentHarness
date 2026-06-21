import asyncio
from contextlib import suppress

from sqlmodel import Session

from app.core.database import engine
from app.scheduler.workers import heartbeat_workers


async def heartbeat_loop(stop_event: asyncio.Event, interval_seconds: int = 10) -> None:
    while not stop_event.is_set():
        # Heartbeat failure should not crash the API process; the next interval
        # can recover after transient database or startup timing issues.
        with suppress(Exception):
            with Session(engine) as session:
                heartbeat_workers(session)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
