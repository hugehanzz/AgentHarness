import asyncio
from contextlib import suppress
from threading import Lock

from sqlmodel import Session, select

from app.core.database import engine
from app.models.common import app_now
from app.models.worker import AgentWorker, WorkerStatus


GEMINI_HEARTBEAT_INTERVAL_SECONDS = 10

_state_lock = Lock()
_active_requests = 0
_batch_failed = False
_batch_offline = False


def is_gemini_active() -> bool:
    with _state_lock:
        return _active_requests > 0


def update_gemini_worker(status: WorkerStatus, heartbeat: bool = True) -> None:
    with Session(engine) as session:
        worker = session.exec(
            select(AgentWorker).where(AgentWorker.worker_key == "gemini")
        ).first()
        if not worker:
            return
        worker.status = status
        worker.last_heartbeat_at = app_now() if heartbeat else None
        session.add(worker)
        session.commit()


def begin_gemini_request() -> None:
    global _active_requests, _batch_failed, _batch_offline
    with _state_lock:
        if _active_requests == 0:
            _batch_failed = False
            _batch_offline = False
        _active_requests += 1
        update_gemini_worker(WorkerStatus.RUNNING)


def finish_gemini_request(*, success: bool, offline: bool = False) -> None:
    global _active_requests, _batch_failed, _batch_offline
    with _state_lock:
        _batch_failed = _batch_failed or not success
        _batch_offline = _batch_offline or offline
        _active_requests = max(0, _active_requests - 1)
        if _active_requests > 0:
            return
        final_status = (
            WorkerStatus.OFFLINE
            if _batch_offline
            else WorkerStatus.FAILED
            if _batch_failed
            else WorkerStatus.ONLINE
        )
        update_gemini_worker(final_status, heartbeat=final_status != WorkerStatus.OFFLINE)


def mark_gemini_offline() -> None:
    with _state_lock:
        if _active_requests > 0:
            return
        update_gemini_worker(WorkerStatus.OFFLINE, heartbeat=False)


async def maintain_gemini_heartbeat(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        if is_gemini_active():
            update_gemini_worker(WorkerStatus.RUNNING)
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=GEMINI_HEARTBEAT_INTERVAL_SECONDS,
            )
        except TimeoutError:
            continue


async def stop_gemini_heartbeat(
    stop_event: asyncio.Event,
    heartbeat_task: asyncio.Task,
) -> None:
    stop_event.set()
    try:
        await asyncio.shield(heartbeat_task)
    except asyncio.CancelledError:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
