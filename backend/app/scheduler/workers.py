from abc import ABC, abstractmethod

from sqlmodel import Session, select

from app.models.common import app_now
from app.models.worker import AgentWorker, WorkerRole, WorkerStatus


class WorkerAgent(ABC):
    name: str
    role: WorkerRole

    @abstractmethod
    async def run(self, payload: dict) -> dict:
        raise NotImplementedError


WORKER_DEFINITIONS = [
    ("Codex", WorkerRole.CODEX, "codex_app_server"),
    ("Claude-DeepSeek", WorkerRole.REVIEWER, "local_cli_agent"),
    ("Gemini", WorkerRole.GEMINI, "planned_agent"),
]

ACTIVE_WORKER_NAMES = {name for name, _role, _worker_type in WORKER_DEFINITIONS}


def ensure_workers(session: Session) -> None:
    for name, role, worker_type in WORKER_DEFINITIONS:
        existing = session.exec(select(AgentWorker).where(AgentWorker.name == name)).first()
        if existing:
            existing.role = role
            existing.worker_type = worker_type
            session.add(existing)
            continue
        session.add(AgentWorker(name=name, role=role, worker_type=worker_type, status=WorkerStatus.IDLE))
    session.commit()


def heartbeat_workers(session: Session) -> None:
    now = app_now()
    workers = session.exec(select(AgentWorker).where(AgentWorker.name.in_(ACTIVE_WORKER_NAMES))).all()
    for worker in workers:
        if worker.worker_type not in {"internal", "local_cli_agent"}:
            continue
        worker.last_heartbeat_at = now
        if worker.status == WorkerStatus.OFFLINE:
            worker.status = WorkerStatus.IDLE
        session.add(worker)
    session.commit()
