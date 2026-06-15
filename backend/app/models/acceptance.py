from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.models.common import utc_now


class AcceptanceStatus(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class AcceptanceItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="task.id")
    title: str = Field(max_length=300)
    description: str | None = None
    status: AcceptanceStatus = Field(default=AcceptanceStatus.PENDING, index=True)
    evidence: str | None = None
    is_auto_checkable: bool = False
    created_at: datetime = Field(default_factory=utc_now)
