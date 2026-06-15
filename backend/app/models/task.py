from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.core.state_machine import TaskStatus
from app.models.common import utc_now


class TaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True, max_length=200)
    description: str
    workspace_path: str | None = Field(default=None, max_length=1000)
    status: TaskStatus = Field(default=TaskStatus.REQUIREMENT_DRAFT, index=True)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None


class TaskEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="task.id")
    event_type: str = Field(index=True, max_length=100)
    from_status: TaskStatus | None = None
    to_status: TaskStatus | None = None
    message: str | None = None
    created_by: str = Field(default="system", max_length=100)
    created_at: datetime = Field(default_factory=utc_now)
