from app.models.worker import WorkerStatus
from app.services import codex_worker_service


def reset_state():
    codex_worker_service._active_runs = 0
    codex_worker_service._batch_failed = False
    codex_worker_service._batch_offline = False


def test_codex_worker_stays_running_until_all_runs_finish(monkeypatch):
    reset_state()
    updates = []
    monkeypatch.setattr(
        codex_worker_service,
        "update_codex_worker",
        lambda session, worker, status, heartbeat=True: updates.append((status, heartbeat)),
    )

    session = object()
    worker = object()
    codex_worker_service.begin_codex_run(session, worker)
    codex_worker_service.begin_codex_run(session, worker)
    codex_worker_service.finish_codex_run(session, worker, success=True)

    assert codex_worker_service.is_codex_active() is True
    assert updates == [
        (WorkerStatus.RUNNING, True),
        (WorkerStatus.RUNNING, True),
    ]

    codex_worker_service.finish_codex_run(session, worker, success=True)

    assert codex_worker_service.is_codex_active() is False
    assert updates[-1] == (WorkerStatus.ONLINE, True)


def test_codex_worker_preserves_failure_across_concurrent_batch(monkeypatch):
    reset_state()
    updates = []
    monkeypatch.setattr(
        codex_worker_service,
        "update_codex_worker",
        lambda session, worker, status, heartbeat=True: updates.append((status, heartbeat)),
    )

    session = object()
    worker = object()
    codex_worker_service.begin_codex_run(session, worker)
    codex_worker_service.begin_codex_run(session, worker)
    codex_worker_service.finish_codex_run(session, worker, success=False)
    codex_worker_service.finish_codex_run(session, worker, success=True)

    assert updates[-1] == (WorkerStatus.FAILED, True)


def test_codex_start_failure_marks_worker_offline(monkeypatch):
    reset_state()
    updates = []
    monkeypatch.setattr(
        codex_worker_service,
        "update_codex_worker",
        lambda session, worker, status, heartbeat=True: updates.append((status, heartbeat)),
    )

    session = object()
    worker = object()
    codex_worker_service.begin_codex_run(session, worker)
    codex_worker_service.finish_codex_run(
        session,
        worker,
        success=False,
        offline=True,
    )

    assert updates[-1] == (WorkerStatus.OFFLINE, False)
