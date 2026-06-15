from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.worker import AgentWorker
from app.schemas.worker import AgentWorkerRead

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=list[AgentWorkerRead])
def list_workers(session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    workers = session.exec(select(AgentWorker).order_by(AgentWorker.name)).all()
    result = []
    for worker in workers:
        is_online = bool(worker.last_heartbeat_at and (now - worker.last_heartbeat_at).total_seconds() < 30)
        result.append(AgentWorkerRead(**worker.model_dump(), is_online=is_online))
    return result
