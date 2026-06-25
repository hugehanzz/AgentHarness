from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.worker import AgentWorker, WorkerStatus
from app.scheduler.workers import ensure_workers, heartbeat_workers


def test_ensure_workers_creates_collaboration_agents():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_workers(session)
        workers = session.exec(select(AgentWorker).order_by(AgentWorker.name)).all()

        assert {worker.name for worker in workers} == {
            "Claude",
            "Codex",
            "Gemini",
        }
        assert {worker.role for worker in workers} == {
            "Developer",
            "Coordinator",
            "Reviewer",
        }
        assert {worker.provider_type for worker in workers} == {
            "codex_app_server",
            "claude_cli",
            "gemini_api",
        }
        assert {worker.worker_key for worker in workers} == {"codex", "claude", "gemini"}


def test_ensure_workers_does_not_overwrite_database_configuration():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        ensure_workers(session)
        claude = session.exec(select(AgentWorker).where(AgentWorker.worker_key == "claude")).one()
        claude.name = "Custom Claude"
        claude.role = "Custom Role"
        session.add(claude)
        session.commit()

        ensure_workers(session)
        session.refresh(claude)

        assert claude.name == "Custom Claude"
        assert claude.role == "Custom Role"


def test_claude_heartbeat_marks_available_cli_online(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    executable = tmp_path / "claude"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "app.scheduler.workers.get_settings",
        lambda: type("Settings", (), {"agent_claude_command": str(executable)})(),
    )

    with Session(engine) as session:
        ensure_workers(session)
        heartbeat_workers(session)
        claude = session.exec(select(AgentWorker).where(AgentWorker.worker_key == "claude")).one()

        assert claude.status == WorkerStatus.ONLINE
        assert claude.last_heartbeat_at is not None


def test_codex_heartbeat_marks_available_command_online(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    executable = tmp_path / "codex"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "app.scheduler.workers.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "codex_app_server_command": f"{executable} app-server",
                "agent_claude_command": None,
                "gemini_api_key": None,
            },
        )(),
    )

    with Session(engine) as session:
        ensure_workers(session)
        heartbeat_workers(session)
        codex = session.exec(select(AgentWorker).where(AgentWorker.worker_key == "codex")).one()

        assert codex.status == WorkerStatus.ONLINE
        assert codex.last_heartbeat_at is not None


def test_codex_stale_running_status_recovers_as_failed(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    executable = tmp_path / "codex"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "app.scheduler.workers.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "codex_app_server_command": f"{executable} app-server",
                "agent_claude_command": None,
                "gemini_api_key": None,
            },
        )(),
    )

    with Session(engine) as session:
        ensure_workers(session)
        codex = session.exec(select(AgentWorker).where(AgentWorker.worker_key == "codex")).one()
        codex.status = WorkerStatus.RUNNING
        codex.last_heartbeat_at = None
        session.add(codex)
        session.commit()

        heartbeat_workers(session)
        session.refresh(codex)

        assert codex.status == WorkerStatus.FAILED
