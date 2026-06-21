import asyncio
import os
import subprocess
import time
from pathlib import Path

from fastapi import HTTPException
from sqlmodel import Session

from app.core.config import get_settings
from app.models.command import CommandRun, CommandStatus


SAFE_COMMANDS: dict[str, list[str]] = {
    "git_status": ["git", "status", "--short"],
    "git_diff_stat": ["git", "diff", "--stat"],
}


async def run_safe_command(session: Session, command_key: str, workspace_path: str, task_id: int | None = None) -> CommandRun:
    # Commands are keyed by server-side registrations so the frontend can never
    # pass arbitrary shell text into subprocess execution.
    if command_key not in SAFE_COMMANDS:
        raise HTTPException(status_code=400, detail="Command is not registered")

    cwd = Path(workspace_path).expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")

    command = SAFE_COMMANDS[command_key]
    record = CommandRun(
        task_id=task_id,
        command_key=command_key,
        command_display=" ".join(command),
        cwd=str(cwd),
        status=CommandStatus.RUNNING,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    start = time.perf_counter()
    try:
        result = await run_registered_command(command, cwd)
        record.exit_code = result.returncode
        record.stdout = result.stdout
        record.stderr = result.stderr
        record.status = CommandStatus.SUCCEEDED if result.returncode == 0 else CommandStatus.FAILED
    except FileNotFoundError:
        record.status = CommandStatus.FAILED
        record.exit_code = None
        executable = command[0]
        record.stderr = (
            f"Executable not found: {executable}. "
            "Ensure the backend process is started with this executable on PATH."
        )
    except OSError as exc:
        record.status = CommandStatus.FAILED
        record.exit_code = None
        record.stderr = f"Failed to start command on {os.name}: {exc}"
    except NotImplementedError:
        record.status = CommandStatus.FAILED
        record.exit_code = None
        record.stderr = (
            "Current asyncio event loop does not support subprocess execution. "
            "On Windows, start the backend with a Proactor event loop."
        )
    except TimeoutError:
        record.status = CommandStatus.TIMED_OUT
        record.stderr = "Command timed out"
    except subprocess.TimeoutExpired:
        record.status = CommandStatus.TIMED_OUT
        record.stderr = "Command timed out"
    finally:
        record.duration_ms = int((time.perf_counter() - start) * 1000)
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


async def run_registered_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    # Prefer asyncio subprocesses; fall back to a thread for event loops that do
    # not support subprocess APIs in the current runtime.
    try:
        return await run_registered_command_async(command, cwd)
    except NotImplementedError:
        return await asyncio.to_thread(run_registered_command_sync, command, cwd)


async def run_registered_command_async(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        proc.communicate(),
        timeout=get_settings().command_timeout_seconds,
    )
    return subprocess.CompletedProcess(
        args=command,
        returncode=proc.returncode or 0,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )


def run_registered_command_sync(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=get_settings().command_timeout_seconds,
        check=False,
    )
