import asyncio
import subprocess

from sqlmodel import Session, SQLModel, create_engine

from app.models.command import CommandStatus
from app.services import command_service
from app.services.command_service import SAFE_COMMANDS, run_safe_command


def test_safe_commands_are_whitelisted():
    assert SAFE_COMMANDS["git_status"] == ["git", "status", "--short"]
    assert SAFE_COMMANDS["git_diff_stat"] == ["git", "diff", "--stat"]
    assert "rm" not in SAFE_COMMANDS


def test_missing_executable_returns_failed_record(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    async def fake_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(command_service.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with Session(engine) as session:
        result = asyncio.run(run_safe_command(session, "git_status", str(tmp_path)))

        assert result.status == CommandStatus.FAILED
        assert result.exit_code is None
        assert result.stderr
        assert "Executable not found: git" in result.stderr


def test_unsupported_event_loop_falls_back_to_sync_subprocess(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    async def fake_create_subprocess_exec(*args, **kwargs):
        raise NotImplementedError()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="clean\n", stderr="")

    monkeypatch.setattr(command_service.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(command_service.subprocess, "run", fake_run)

    with Session(engine) as session:
        result = asyncio.run(run_safe_command(session, "git_status", str(tmp_path)))

        assert result.status == CommandStatus.SUCCEEDED
        assert result.exit_code == 0
        assert result.stdout == "clean\n"
