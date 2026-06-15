from datetime import datetime

from pydantic import BaseModel

from app.models.acceptance import AcceptanceStatus


class AcceptanceItemCreate(BaseModel):
    title: str
    description: str | None = None
    is_auto_checkable: bool = False


class AcceptanceItemUpdate(BaseModel):
    status: AcceptanceStatus
    evidence: str | None = None


class AcceptanceItemRead(BaseModel):
    id: int
    task_id: int
    title: str
    description: str | None
    status: AcceptanceStatus
    evidence: str | None
    is_auto_checkable: bool
    created_at: datetime
