from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.common import app_now
from app.models.worker import AgentWorker
from app.schemas.worker import AgentWorkerRead

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=list[AgentWorkerRead])
def list_workers(session: Session = Depends(get_session)):
    now = app_now()
    workers = session.exec(select(AgentWorker).order_by(AgentWorker.name)).all()
    result = []
    for worker in workers:
        heartbeat_at = worker.last_heartbeat_at
        if heartbeat_at and heartbeat_at.tzinfo is not None:
            heartbeat_at = heartbeat_at.replace(tzinfo=None)
        is_online = bool(heartbeat_at and (now - heartbeat_at).total_seconds() < 30)
        result.append(AgentWorkerRead(**worker.model_dump(), is_online=is_online))
    return result
