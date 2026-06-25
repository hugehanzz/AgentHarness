import asyncio
from contextlib import suppress

from sqlmodel import Session

from app.core.database import engine
from app.scheduler.workers import heartbeat_workers


async def heartbeat_loop(stop_event: asyncio.Event, interval_seconds: int = 10) -> None:
    while not stop_event.is_set():
        # 心跳失败不应导致 API 进程崩溃；下一个间隔可以在短暂的数据库或启动时序问题后恢复。
        with suppress(Exception):
            with Session(engine) as session:
                heartbeat_workers(session)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
