from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, Enum as SAEnum, Text
from sqlmodel import Field, SQLModel

from app.core.state_machine import TaskStatus
from app.models.common import app_now


class TaskMode(StrEnum):
    SECRETARY = "secretary"
    COORDINATOR = "coordinator"


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True, max_length=200)
    description: str = Field(sa_column=Column(Text))
    workspace_path: str | None = Field(default=None, max_length=1000)
    status: TaskStatus = Field(default=TaskStatus.REQUIREMENT_DRAFT, index=True)
    mode: TaskMode = Field(
        default=TaskMode.SECRETARY,
        sa_column=Column(
            SAEnum(TaskMode, values_callable=lambda items: [item.value for item in items], native_enum=False, length=32),
            nullable=False,
            default=TaskMode.SECRETARY.value,
        ),
    )
    created_at: datetime = Field(default_factory=app_now)
    updated_at: datetime = Field(default_factory=app_now)
    archived_at: datetime | None = None


class TaskEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="task.id")
    event_type: str = Field(index=True, max_length=100)
    from_status: TaskStatus | None = None
    to_status: TaskStatus | None = None
    message: str | None = Field(default=None, sa_column=Column(Text))
    created_by: str = Field(default="system", max_length=100)
    created_at: datetime = Field(default_factory=app_now)
