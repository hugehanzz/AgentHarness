from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

from app.models.common import app_now


class CommandStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class CommandRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: int | None = Field(default=None, index=True, foreign_key="task.id")
    command_key: str = Field(index=True, max_length=100)
    command_display: str = Field(max_length=500)
    cwd: str = Field(max_length=1000)
    exit_code: int | None = None
    stdout: str | None = Field(default=None, sa_column=Column(Text))
    stderr: str | None = Field(default=None, sa_column=Column(Text))
    duration_ms: int | None = None
    status: CommandStatus = Field(default=CommandStatus.RUNNING, index=True)
    created_at: datetime = Field(default_factory=app_now)
