import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.task import TaskEvent
from app.models.worker import AgentRun, AgentSession, AgentSessionStatus, RunStatus
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
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(agent_claude_command="claude", agent_timeout_seconds=5),
    )

    def fake_run(command, **kwargs):
        assert command[:2] == ["claude", "-p"]
        assert "--resume" not in command
        assert "任务标题：Build task" in kwargs["input"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "审查完成",
                    "session_id": "claude-session-1",
                    "uuid": "turn-1",
                    "permission_denials": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(agent_run_service.subprocess, "run", fake_run)

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Build task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_local_agent(session, task.id, "claude_review"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.exit_code == 0
        assert run.provider_type == "claude_cli"
        assert run.output_payload == "审查完成"
        assert run.external_thread_id == "claude-session-1"
        assert run.external_turn_id == "turn-1"
        assert run.agent_session_id is not None
        saved_run = session.exec(select(AgentRun).where(AgentRun.task_id == task.id)).one()
        assert saved_run.input_payload and "任务标题：Build task" in saved_run.input_payload
        saved_session = session.get(AgentSession, run.agent_session_id)
        assert saved_session
        assert saved_session.external_session_id == "claude-session-1"
        assert saved_session.task_count == 1
        event = session.exec(select(TaskEvent).where(TaskEvent.task_id == task.id)).all()[-1]
        assert event.event_type == "AGENT_RUN_COMPLETED"


def test_run_local_agent_uses_prompt_override(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(agent_claude_command="claude", agent_timeout_seconds=5),
    )

    def fake_run(command, **kwargs):
        assert kwargs["input"] == "custom review prompt"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "review ready",
                    "session_id": "claude-session-1",
                    "uuid": "turn-1",
                    "permission_denials": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(agent_run_service.subprocess, "run", fake_run)

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Review task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_local_agent(session, task.id, "claude_review", "custom review prompt"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.input_payload == "custom review prompt"


def test_claude_recheck_reuses_task_session_without_incrementing(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(agent_claude_command="claude", agent_timeout_seconds=5),
    )
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "ok",
                    "session_id": "claude-session-1",
                    "uuid": f"turn-{len(commands)}",
                    "permission_denials": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(agent_run_service.subprocess, "run", fake_run)

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Review task", description="Requirement", workspace_path=str(tmp_path)),
        )

        review_run = asyncio.run(run_local_agent(session, task.id, "claude_review"))
        recheck_run = asyncio.run(run_local_agent(session, task.id, "claude_recheck"))

        assert review_run.agent_session_id == recheck_run.agent_session_id
        assert "--resume" not in commands[0]
        assert commands[1][-2:] == ["--resume", "claude-session-1"]
        saved_session = session.get(AgentSession, review_run.agent_session_id)
        assert saved_session
        assert saved_session.task_count == 1


def test_claude_session_rotates_after_five_distinct_tasks(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(agent_claude_command="claude", agent_timeout_seconds=5),
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        session_id = "claude-session-2" if len(calls) == 1 else "claude-session-unexpected"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": "ok",
                    "session_id": session_id,
                    "uuid": "turn",
                    "permission_denials": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(agent_run_service.subprocess, "run", fake_run)

    with Session(engine) as session:
        ensure_workers(session)
        existing_session = AgentSession(
            provider_type="claude_cli",
            workspace_path=str(tmp_path.resolve()),
            external_session_id="claude-session-1",
            task_count=5,
            status=AgentSessionStatus.ACTIVE,
        )
        session.add(existing_session)
        session.commit()
        task = create_task(
            session,
            TaskCreate(title="Sixth task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_local_agent(session, task.id, "claude_review"))

        assert "--resume" not in calls[0]
        assert run.external_thread_id == "claude-session-2"
        rotated_session = session.get(AgentSession, existing_session.id)
        assert rotated_session
        assert rotated_session.status == AgentSessionStatus.ROTATED
        new_session = session.get(AgentSession, run.agent_session_id)
        assert new_session
        assert new_session.external_session_id == "claude-session-2"
        assert new_session.task_count == 1


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


def test_codex_run_uses_prompt_override(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(codex_app_server_command="codex app-server", agent_timeout_seconds=5),
    )

    class FakeCodexAppServerProcess:
        received_prompt = None

        @classmethod
        async def start(cls, command, cwd):
            return cls()

        async def run_turn(self, prompt, cwd, thread_id, run_type):
            FakeCodexAppServerProcess.received_prompt = prompt
            return {
                "thread_id": "thread-override",
                "turn_id": "turn-override",
                "agent_text": "override ready",
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
            TaskCreate(title="Override task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_agent(session, task.id, "codex_implement", "  custom prompt  "))

        assert run.status == RunStatus.SUCCEEDED
        assert run.input_payload == "custom prompt"
        assert FakeCodexAppServerProcess.received_prompt == "custom prompt"


def test_codex_acceptance_checklist_run_uses_acceptance_prompt(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(codex_app_server_command="codex app-server", agent_timeout_seconds=5),
    )

    class FakeCodexAppServerProcess:
        received_prompt = None
        received_run_type = None

        @classmethod
        async def start(cls, command, cwd):
            return cls()

        async def run_turn(self, prompt, cwd, thread_id, run_type):
            FakeCodexAppServerProcess.received_prompt = prompt
            FakeCodexAppServerProcess.received_run_type = run_type
            return {
                "thread_id": "thread-acceptance",
                "turn_id": "turn-acceptance",
                "agent_text": "验收建议",
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
            TaskCreate(title="Acceptance task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_agent(session, task.id, "codex_acceptance_checklist"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.provider_type == "codex_app_server"
        assert run.output_payload == "验收建议"
        assert FakeCodexAppServerProcess.received_run_type == "codex_acceptance_checklist"
        assert FakeCodexAppServerProcess.received_prompt
        assert "Human Supervisor" in FakeCodexAppServerProcess.received_prompt
        assert "Apifox" in FakeCodexAppServerProcess.received_prompt
        saved_items = session.exec(select(AgentRun).where(AgentRun.task_id == task.id)).all()
        assert len(saved_items) == 1


def test_codex_archive_run_records_archive_check(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(codex_app_server_command="codex app-server", agent_timeout_seconds=5),
    )
    monkeypatch.setattr(
        agent_run_service,
        "check_readme_archive",
        lambda workspace_path: {
            "readme_path": str(tmp_path / "README.md"),
            "readme_paths": [str(tmp_path / "README.md")],
            "has_acceptance_status": True,
            "has_test_results": True,
            "has_archive_notes": True,
            "has_next_steps": True,
        },
    )

    class FakeCodexAppServerProcess:
        @classmethod
        async def start(cls, command, cwd):
            return cls()

        async def run_turn(self, prompt, cwd, thread_id, run_type):
            assert run_type == "codex_archive"
            assert "README" in prompt
            assert "归档" in prompt
            return {
                "thread_id": "thread-archive",
                "turn_id": "turn-archive",
                "agent_text": "archive ready",
                "diagnostics": "codex diagnostics",
                "completed": True,
            }

        async def stop(self):
            pass

    monkeypatch.setattr(agent_run_service, "CodexAppServerProcess", FakeCodexAppServerProcess)

    with Session(engine) as session:
        ensure_workers(session)
        task = create_task(
            session,
            TaskCreate(title="Archive task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_agent(session, task.id, "codex_archive"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.external_thread_id == "thread-archive"
        assert run.output_payload == "archive ready"
        assert run.stderr and "codex diagnostics" in run.stderr
        assert "archive_check" in run.stderr
        assert "has_archive_notes" in run.stderr


def test_codex_archive_run_keeps_success_when_archive_check_is_incomplete(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(codex_app_server_command="codex app-server", agent_timeout_seconds=5),
    )
    monkeypatch.setattr(
        agent_run_service,
        "check_readme_archive",
        lambda workspace_path: {
            "readme_path": str(tmp_path / "README.md"),
            "readme_paths": [str(tmp_path / "README.md")],
            "has_acceptance_status": True,
            "has_test_results": False,
            "has_archive_notes": True,
            "has_next_steps": True,
        },
    )

    class FakeCodexAppServerProcess:
        @classmethod
        async def start(cls, command, cwd):
            return cls()

        async def run_turn(self, prompt, cwd, thread_id, run_type):
            return {
                "thread_id": "thread-archive",
                "turn_id": "turn-archive",
                "agent_text": "archive ready",
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
            TaskCreate(title="Archive task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_agent(session, task.id, "codex_archive"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.error_message is None
        assert run.stderr and "archive_check" in run.stderr
        assert "archive_check_warning" in run.stderr
        assert "has_test_results" in run.stderr


def test_codex_archive_run_keeps_success_when_archive_check_errors(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        agent_run_service,
        "get_settings",
        lambda: SimpleNamespace(codex_app_server_command="codex app-server", agent_timeout_seconds=5),
    )

    def raise_archive_error(workspace_path):
        raise HTTPException(status_code=404, detail="README.md not found")

    monkeypatch.setattr(agent_run_service, "check_readme_archive", raise_archive_error)

    class FakeCodexAppServerProcess:
        @classmethod
        async def start(cls, command, cwd):
            return cls()

        async def run_turn(self, prompt, cwd, thread_id, run_type):
            return {
                "thread_id": "thread-archive",
                "turn_id": "turn-archive",
                "agent_text": "archive ready",
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
            TaskCreate(title="Archive task", description="Requirement", workspace_path=str(tmp_path)),
        )

        run = asyncio.run(run_agent(session, task.id, "codex_archive"))

        assert run.status == RunStatus.SUCCEEDED
        assert run.error_message is None
        assert run.stderr and "archive_check_error" in run.stderr
        assert "README.md not found" in run.stderr


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
