from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.worker import AgentWorker
from app.schemas.worker import AgentWorkerRead

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=list[AgentWorkerRead])
def list_workers(session: Session = Depends(get_session)):
    return session.exec(select(AgentWorker).order_by(AgentWorker.id)).all()
