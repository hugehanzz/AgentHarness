import asyncio
import os
import shlex
from pathlib import Path

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.common import app_now
from app.models.prompt import PromptType
from app.models.task import TaskEvent
from app.models.worker import AgentRun, AgentWorker, RunStatus
from app.prompts.templates import build_prompt
from app.services.task_service import get_task_or_404


CODEX_APP_SERVER_RUN_TYPES = {
    "codex_plan",
    "codex_implement",
    "codex_fix",
}


LOCAL_CLI_RUN_DEFINITIONS: dict[str, dict[str, str]] = {
    "claude_review": {
        "worker_name": "Claude-DeepSeek",
        "prompt_type": PromptType.CLAUDE_REVIEW,
        "command_setting": "agent_claude_command",
    },
    "claude_recheck": {
        "worker_name": "Claude-DeepSeek",
        "prompt_type": PromptType.CLAUDE_RECHECK,
        "command_setting": "agent_claude_command",
    },
}


def split_command(command_value: str) -> list[str]:
    if os.name == "nt":
        parts = shlex.split(command_value, posix=False)
        return [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'" else part
            for part in parts
        ]
    return shlex.split(command_value)


def list_agent_runs(session: Session, task_id: int) -> list[AgentRun]:
    get_task_or_404(session, task_id)
    return list(
        session.exec(
            select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.created_at.desc())
        ).all()
    )


async def run_local_agent(session: Session, task_id: int, run_type: str) -> AgentRun:
    if run_type in CODEX_APP_SERVER_RUN_TYPES:
        raise HTTPException(status_code=501, detail="Codex App Server adapter is not implemented yet")
    if run_type not in LOCAL_CLI_RUN_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Agent run type is not registered")

    task = get_task_or_404(session, task_id)
    if not task.workspace_path:
        raise HTTPException(status_code=400, detail="Task workspace_path is required")

    cwd = Path(task.workspace_path).expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise HTTPException(status_code=400, detail="workspace_path must be an existing directory")

    definition = LOCAL_CLI_RUN_DEFINITIONS[run_type]
    settings = get_settings()
    command_value = getattr(settings, definition["command_setting"])
    if not command_value:
        raise HTTPException(
            status_code=400,
            detail=f"{definition['command_setting'].upper()} is not configured",
        )

    command = split_command(command_value)
    if not command:
        raise HTTPException(status_code=400, detail="Configured agent command is empty")

    worker = session.exec(select(AgentWorker).where(AgentWorker.name == definition["worker_name"])).first()
    prompt_type = PromptType(definition["prompt_type"])
    prompt = build_prompt(task, prompt_type)
    now = app_now()
    record = AgentRun(
        task_id=task.id,
        worker_id=worker.id if worker else None,
        run_type=run_type,
        provider_type="local_cli",
        command_display=" ".join(command),
        cwd=str(cwd),
        status=RunStatus.RUNNING,
        input_payload=prompt,
        started_at=now,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(prompt.encode("utf-8")),
            timeout=settings.agent_timeout_seconds,
        )
        record.exit_code = proc.returncode
        record.output_payload = stdout_bytes.decode("utf-8", errors="replace")
        record.stderr = stderr_bytes.decode("utf-8", errors="replace")
        record.status = RunStatus.SUCCEEDED if proc.returncode == 0 else RunStatus.FAILED
    except TimeoutError:
        record.status = RunStatus.TIMED_OUT
        record.error_message = "Agent command timed out"
    except OSError as exc:
        record.status = RunStatus.FAILED
        record.error_message = str(exc)
    finally:
        record.finished_at = app_now()
        session.add(record)
        session.add(
            TaskEvent(
                task_id=task.id,
                event_type="AGENT_RUN_COMPLETED",
                message=f"{run_type}: {record.status}",
                created_by="agentharness",
            )
        )
        session.commit()
        session.refresh(record)

    return record
