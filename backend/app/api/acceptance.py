from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.acceptance import AcceptanceItem
from app.schemas.acceptance import AcceptanceItemCreate, AcceptanceItemRead, AcceptanceItemUpdate

router = APIRouter(prefix="/tasks/{task_id}/acceptance", tags=["acceptance"])


@router.get("", response_model=list[AcceptanceItemRead])
def list_items(task_id: int, session: Session = Depends(get_session)):
    return list(session.exec(select(AcceptanceItem).where(AcceptanceItem.task_id == task_id)).all())


@router.post("", response_model=AcceptanceItemRead)
def create_item(task_id: int, payload: AcceptanceItemCreate, session: Session = Depends(get_session)):
    item = AcceptanceItem(task_id=task_id, **payload.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/{item_id}", response_model=AcceptanceItemRead)
def update_item(task_id: int, item_id: int, payload: AcceptanceItemUpdate, session: Session = Depends(get_session)):
    item = session.get(AcceptanceItem, item_id)
    if not item or item.task_id != task_id:
        raise HTTPException(status_code=404, detail="Acceptance item not found")
    item.status = payload.status
    item.evidence = payload.evidence
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
