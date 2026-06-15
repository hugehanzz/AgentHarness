import asyncio
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
        record.exit_code = proc.returncode
        record.stdout = stdout_bytes.decode("utf-8", errors="replace")
        record.stderr = stderr_bytes.decode("utf-8", errors="replace")
        record.status = CommandStatus.SUCCEEDED if proc.returncode == 0 else CommandStatus.FAILED
    except TimeoutError:
        record.status = CommandStatus.TIMED_OUT
        record.stderr = "Command timed out"
    finally:
        record.duration_ms = int((time.perf_counter() - start) * 1000)
        session.add(record)
        session.commit()
        session.refresh(record)
    return record
