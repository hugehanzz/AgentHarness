import asyncio
from contextlib import suppress
from threading import Lock

from sqlmodel import Session

from app.models.common import app_now
from app.models.worker import AgentWorker, WorkerStatus


CODEX_HEARTBEAT_INTERVAL_SECONDS = 10

_state_lock = Lock()
_active_runs = 0
_batch_failed = False
_batch_offline = False


def is_codex_active() -> bool:
    with _state_lock:
        return _active_runs > 0


def update_codex_worker(
    session: Session,
    worker: AgentWorker,
    status: WorkerStatus,
    heartbeat: bool = True,
) -> None:
    worker.status = status
    worker.last_heartbeat_at = app_now() if heartbeat else None
    session.add(worker)
    session.commit()


def begin_codex_run(session: Session, worker: AgentWorker) -> None:
    global _active_runs, _batch_failed, _batch_offline
    with _state_lock:
        if _active_runs == 0:
            _batch_failed = False
            _batch_offline = False
        _active_runs += 1
        update_codex_worker(session, worker, WorkerStatus.RUNNING)


def finish_codex_run(
    session: Session,
    worker: AgentWorker,
    *,
    success: bool,
    offline: bool = False,
) -> None:
    global _active_runs, _batch_failed, _batch_offline
    with _state_lock:
        _batch_failed = _batch_failed or not success
        _batch_offline = _batch_offline or offline
        _active_runs = max(0, _active_runs - 1)
        if _active_runs > 0:
            return
        final_status = (
            WorkerStatus.OFFLINE
            if _batch_offline
            else WorkerStatus.FAILED
            if _batch_failed
            else WorkerStatus.ONLINE
        )
        update_codex_worker(
            session,
            worker,
            final_status,
            heartbeat=final_status != WorkerStatus.OFFLINE,
        )


async def maintain_codex_heartbeat(
    session: Session,
    worker: AgentWorker,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        if is_codex_active():
            update_codex_worker(session, worker, WorkerStatus.RUNNING)
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=CODEX_HEARTBEAT_INTERVAL_SECONDS,
            )
        except TimeoutError:
            continue


async def stop_codex_heartbeat(
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
