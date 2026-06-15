from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.worker import AgentWorker, WorkerRole, WorkerStatus


class WorkerAgent(ABC):
    name: str
    role: WorkerRole

    @abstractmethod
    async def run(self, payload: dict) -> dict:
        raise NotImplementedError


WORKER_DEFINITIONS = [
    ("PromptBuilderWorker", WorkerRole.ORCHESTRATOR),
    ("ReviewParserWorker", WorkerRole.REVIEW_PARSER),
    ("CommandWorker", WorkerRole.COMMAND),
    ("ArchiveCheckWorker", WorkerRole.ARCHIVE_CHECK),
]


def ensure_workers(session: Session) -> None:
    for name, role in WORKER_DEFINITIONS:
        existing = session.exec(select(AgentWorker).where(AgentWorker.name == name)).first()
        if existing:
            continue
        session.add(AgentWorker(name=name, role=role, worker_type="internal", status=WorkerStatus.IDLE))
    session.commit()


def heartbeat_workers(session: Session) -> None:
    now = datetime.now(timezone.utc)
    workers = session.exec(select(AgentWorker)).all()
    for worker in workers:
        worker.last_heartbeat_at = now
        if worker.status == WorkerStatus.OFFLINE:
            worker.status = WorkerStatus.IDLE
        session.add(worker)
    session.commit()
