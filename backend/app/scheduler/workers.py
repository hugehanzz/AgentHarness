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
    ("Orchestrator", WorkerRole.ORCHESTRATOR, "external_llm_planned"),
    ("Codex", WorkerRole.DEVELOPER, "external_human_loop"),
    ("Claude-DeepSeek", WorkerRole.REVIEWER, "external_human_loop"),
    ("Human Supervisor", WorkerRole.ACCEPTANCE, "human_gate"),
]


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
    workers = session.exec(select(AgentWorker)).all()
    for worker in workers:
        if worker.worker_type.startswith("external") or worker.worker_type == "human_gate":
            continue
        worker.last_heartbeat_at = now
        if worker.status == WorkerStatus.OFFLINE:
            worker.status = WorkerStatus.IDLE
        session.add(worker)
    session.commit()
