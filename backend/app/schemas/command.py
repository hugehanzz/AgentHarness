from datetime import datetime

from pydantic import BaseModel

from app.models.command import CommandStatus


class CommandRunRequest(BaseModel):
    command_key: str
    workspace_path: str
    task_id: int | None = None


class CommandRunRead(BaseModel):
    id: int
    task_id: int | None
    command_key: str
    command_display: str
    cwd: str
    exit_code: int | None
    stdout: str | None
    stderr: str | None
    duration_ms: int | None
    status: CommandStatus
    created_at: datetime
