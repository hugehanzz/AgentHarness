from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.worker import RunStatus


class AgentRunCreate(BaseModel):
    run_type: str


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    worker_id: int | None
    agent_session_id: int | None
    run_type: str
    provider_type: str
    external_thread_id: str | None
    external_turn_id: str | None
    command_display: str | None
    cwd: str | None
    exit_code: int | None
    status: RunStatus
    input_payload: str | None
    output_payload: str | None
    stderr: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
