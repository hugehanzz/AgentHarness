from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.worker import AgentWorker, WorkerRole
from app.scheduler.workers import ensure_workers, heartbeat_workers


def test_ensure_workers_creates_collaboration_agents():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_workers(session)
        workers = session.exec(select(AgentWorker).order_by(AgentWorker.name)).all()

        assert {worker.name for worker in workers} == {
            "Claude-DeepSeek",
            "Codex",
            "Gemini",
        }
        assert {worker.role for worker in workers} == {
            WorkerRole.CODEX,
            WorkerRole.GEMINI,
            WorkerRole.REVIEWER,
        }
        assert {worker.worker_type for worker in workers} == {
            "codex_app_server",
            "local_cli_agent",
            "planned_agent",
        }


def test_human_and_external_agents_do_not_receive_fake_heartbeat():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_workers(session)
        heartbeat_workers(session)
        workers = session.exec(select(AgentWorker)).all()

        skipped_workers = [worker for worker in workers if worker.worker_type != "local_cli_agent"]
        local_cli_workers = [worker for worker in workers if worker.worker_type == "local_cli_agent"]

        assert all(worker.last_heartbeat_at is None for worker in skipped_workers)
        assert all(worker.last_heartbeat_at is not None for worker in local_cli_workers)
