from abc import ABC, abstractmethod
import os
from pathlib import Path
import shlex
import shutil

from sqlmodel import Session, select

from app.core.config import get_settings
from app.models.common import app_now
from app.models.worker import AgentWorker, WorkerStatus
from app.services.gemini_worker_service import is_gemini_active


class WorkerAgent(ABC):
    name: str
    role: str

    @abstractmethod
    async def run(self, payload: dict) -> dict:
        raise NotImplementedError


WORKER_DEFINITIONS = [
    ("codex", "Codex", "Developer", "codex_app_server"),
    ("claude", "Claude", "Reviewer", "claude_cli"),
    ("gemini", "Gemini", "Coordinator", "gemini_api"),
]


def ensure_workers(session: Session) -> None:
    # The database is the source of truth after initial installation. Seed
    # defaults only when the table is completely empty; never overwrite edits.
    if session.exec(select(AgentWorker.id).limit(1)).first() is not None:
        return
    for worker_key, name, role, provider_type in WORKER_DEFINITIONS:
        session.add(
            AgentWorker(
                worker_key=worker_key,
                name=name,
                role=role,
                provider_type=provider_type,
                status=WorkerStatus.OFFLINE,
            )
        )
    session.commit()


def command_is_available(command_value: str | None) -> bool:
    if not command_value:
        return False
    command = shlex.split(command_value, posix=os.name != "nt")
    if os.name == "nt":
        command = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'" else part
            for part in command
        ]
    if not command:
        return False
    executable = Path(command[0]).expanduser()
    if executable.is_absolute():
        return executable.is_file()
    return shutil.which(command[0]) is not None


def heartbeat_workers(session: Session) -> None:
    # Claude is an on-demand CLI, not a permanent daemon. Its idle heartbeat
    # means the configured executable is locally available. Codex and Gemini
    # will get provider-specific probes in their own implementations.
    settings = get_settings()
    claude = session.exec(select(AgentWorker).where(AgentWorker.worker_key == "claude")).first()
    if claude and claude.status != WorkerStatus.RUNNING:
        available = command_is_available(settings.agent_claude_command)
        claude.last_heartbeat_at = app_now() if available else None
        if available and claude.status == WorkerStatus.OFFLINE:
            claude.status = WorkerStatus.ONLINE
        elif not available:
            claude.status = WorkerStatus.OFFLINE
        session.add(claude)

    gemini = session.exec(select(AgentWorker).where(AgentWorker.worker_key == "gemini")).first()
    if gemini and not is_gemini_active():
        if getattr(settings, "gemini_api_key", None):
            gemini.last_heartbeat_at = app_now()
            if gemini.status in {WorkerStatus.OFFLINE, WorkerStatus.RUNNING}:
                gemini.status = WorkerStatus.ONLINE
        else:
            gemini.status = WorkerStatus.OFFLINE
            gemini.last_heartbeat_at = None
        session.add(gemini)
    session.commit()
