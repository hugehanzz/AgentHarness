from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.models.common import app_now


class ReviewSeverity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ReviewItemStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    WONT_FIX = "WONT_FIX"


class ReviewItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: int | None = Field(default=None, index=True, foreign_key="task.id")
    severity: ReviewSeverity = Field(default=ReviewSeverity.UNKNOWN, index=True)
    title: str = Field(max_length=300)
    description: str | None = None
    status: ReviewItemStatus = Field(default=ReviewItemStatus.OPEN, index=True)
    source_file: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=app_now)
