import asyncio
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.task import TaskEvent
from app.models.worker import AgentRun, RunStatus
from app.scheduler.workers import ensure_workers
from app.schemas.task import TaskCreate
from app.services import agent_run_service
from app.services.agent_run_service import run_agent, run_local_agent, split_command
from app.services.task_service import create_task


def test_run_local_agent_requires_configured_command(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(agent_claude_command=None, agent_timeout_seconds=5),
    )

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Plan task", description="Requirement", workspace_path=str(tmp_path)),
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(run_local_agent(session, task.id, "claude_review"))

        assert exc_info.value.status_code == 400
        assert "AGENT_CLAUDE_COMMAND" in exc_info.value.detail


def test_run_local_agent_records_cli_output(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    script = "import sys; data=sys.stdin.read(); print('received=' + str('任务标题：Build task' in data))"
    command = f'"{sys.executable}" -c "{script}"'
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(agent_claude_command=command, agent_timeout_seconds=5),
    )

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Build task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_local_agent(session, task.id, "claude_review"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.exit_code == 0
        assert run.provider_type == "local_cli"
        assert "received=True" in (run.output_payload or "")
        saved_run = session.exec(select(AgentRun).where(AgentRun.task_id == task.id)).one()
        assert saved_run.input_payload and "任务标题：Build task" in saved_run.input_payload
        event = session.exec(select(TaskEvent).where(TaskEvent.task_id == task.id)).all()[-1]
        assert event.event_type == "AGENT_RUN_COMPLETED"


def test_codex_run_uses_app_server_adapter(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(codex_app_server_command="codex app-server", agent_timeout_seconds=5),
    )

    class FakeCodexAppServerProcess:
        command = None
        cwd = None
        stopped = False

        @classmethod
        async def start(cls, command, cwd):
            cls.command = command
            cls.cwd = cwd
            return cls()

        async def run_turn(self, prompt, cwd, thread_id, run_type):
            assert "任务标题：Plan task" in prompt
            assert thread_id is None
            assert run_type == "codex_plan"
            return {
                "thread_id": "thread-1",
                "turn_id": "turn-1",
                "agent_text": "plan ready",
                "diagnostics": None,
                "completed": True,
            }

        async def stop(self):
            FakeCodexAppServerProcess.stopped = True

    monkeypatch.setattr(agent_run_service, "CodexAppServerProcess", FakeCodexAppServerProcess)

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Plan task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_agent(session, task.id, "codex_plan"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.provider_type == "codex_app_server"
        assert run.external_thread_id == "thread-1"
        assert run.external_turn_id == "turn-1"
        assert run.output_payload == "plan ready"
        assert FakeCodexAppServerProcess.command == ["codex", "app-server"]
        assert FakeCodexAppServerProcess.cwd == str(tmp_path.resolve())
        assert FakeCodexAppServerProcess.stopped is True


def test_codex_run_reuses_latest_thread(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(codex_app_server_command="codex app-server", agent_timeout_seconds=5),
    )

    class FakeCodexAppServerProcess:
        received_thread_id = None

        @classmethod
        async def start(cls, command, cwd):
            return cls()

        async def run_turn(self, prompt, cwd, thread_id, run_type):
            FakeCodexAppServerProcess.received_thread_id = thread_id
            assert run_type == "codex_fix"
            return {
                "thread_id": thread_id,
                "turn_id": "turn-2",
                "agent_text": "fix ready",
                "diagnostics": None,
                "completed": True,
            }

        async def stop(self):
            pass

    monkeypatch.setattr(agent_run_service, "CodexAppServerProcess", FakeCodexAppServerProcess)

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Fix task", description="Requirement", workspace_path=str(tmp_path)),
        )
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="codex_plan",
                provider_type="codex_app_server",
                external_thread_id="thread-existing",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()

        run = asyncio.run(run_agent(session, task.id, "codex_fix"))

        assert FakeCodexAppServerProcess.received_thread_id == "thread-existing"
        assert run.external_thread_id == "thread-existing"
        assert run.external_turn_id == "turn-2"


def test_split_command_preserves_windows_backslashes(monkeypatch):
    monkeypatch.setattr(agent_run_service.os, "name", "nt")

    assert split_command(r'powershell -NoProfile -File D:\NodeJS\codex.ps1') == [
        "powershell",
        "-NoProfile",
        "-File",
        r"D:\NodeJS\codex.ps1",
    ]
    assert split_command(r'"C:\Program Files\Claude\claude.exe" --print') == [
        r"C:\Program Files\Claude\claude.exe",
        "--print",
    ]
