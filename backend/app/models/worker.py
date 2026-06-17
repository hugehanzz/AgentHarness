from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.models.common import app_now


class WorkerRole(StrEnum):
    ORCHESTRATOR = "ORCHESTRATOR"
    DEVELOPER = "DEVELOPER"
    REVIEWER = "REVIEWER"
    ACCEPTANCE = "ACCEPTANCE"
    COMMAND = "COMMAND"
    REVIEW_PARSER = "REVIEW_PARSER"
    ARCHIVE_CHECK = "ARCHIVE_CHECK"


class WorkerStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    OFFLINE = "OFFLINE"
    FAILED = "FAILED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class AgentWorker(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=120)
    role: WorkerRole = Field(index=True)
    worker_type: str = Field(default="internal", max_length=80)
    status: WorkerStatus = Field(default=WorkerStatus.IDLE, index=True)
    last_heartbeat_at: datetime | None = None
    current_task_id: int | None = Field(default=None, foreign_key="task.id")
    created_at: datetime = Field(default_factory=app_now)


class AgentRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: int | None = Field(default=None, index=True, foreign_key="task.id")
    worker_id: int | None = Field(default=None, index=True, foreign_key="agentworker.id")
    run_type: str = Field(index=True, max_length=100)
    provider_type: str = Field(default="local_cli", index=True, max_length=80)
    external_thread_id: str | None = Field(default=None, index=True, max_length=120)
    external_turn_id: str | None = Field(default=None, index=True, max_length=120)
    command_display: str | None = Field(default=None, max_length=500)
    cwd: str | None = Field(default=None, max_length=1000)
    exit_code: int | None = None
    status: RunStatus = Field(default=RunStatus.QUEUED, index=True)
    input_payload: str | None = None
    output_payload: str | None = None
    stderr: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=app_now)
