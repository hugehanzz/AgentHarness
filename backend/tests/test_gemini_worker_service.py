from app.models.worker import WorkerStatus
from app.services import gemini_worker_service


def reset_state():
    gemini_worker_service._active_requests = 0
    gemini_worker_service._batch_failed = False
    gemini_worker_service._batch_offline = False


def test_gemini_worker_stays_running_until_all_requests_finish(monkeypatch):
    reset_state()
    updates = []
    monkeypatch.setattr(
        gemini_worker_service,
        "update_gemini_worker",
        lambda status, heartbeat=True: updates.append((status, heartbeat)),
    )

    gemini_worker_service.begin_gemini_request()
    gemini_worker_service.begin_gemini_request()
    gemini_worker_service.finish_gemini_request(success=True)

    assert gemini_worker_service.is_gemini_active() is True
    assert updates == [
        (WorkerStatus.RUNNING, True),
        (WorkerStatus.RUNNING, True),
    ]

    gemini_worker_service.finish_gemini_request(success=True)

    assert gemini_worker_service.is_gemini_active() is False
    assert updates[-1] == (WorkerStatus.ONLINE, True)


def test_gemini_worker_preserves_failure_across_concurrent_batch(monkeypatch):
    reset_state()
    updates = []
    monkeypatch.setattr(
        gemini_worker_service,
        "update_gemini_worker",
        lambda status, heartbeat=True: updates.append((status, heartbeat)),
    )

    gemini_worker_service.begin_gemini_request()
    gemini_worker_service.begin_gemini_request()
    gemini_worker_service.finish_gemini_request(success=False)
    gemini_worker_service.finish_gemini_request(success=True)

    assert updates[-1] == (WorkerStatus.FAILED, True)


def test_mark_gemini_offline_clears_heartbeat(monkeypatch):
    reset_state()
    updates = []
    monkeypatch.setattr(
        gemini_worker_service,
        "update_gemini_worker",
        lambda status, heartbeat=True: updates.append((status, heartbeat)),
    )

    gemini_worker_service.mark_gemini_offline()

    assert updates == [(WorkerStatus.OFFLINE, False)]
