from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.state_machine import TaskStatus
from app.models.task import TaskPriority


class TaskCreate(BaseModel):
    title: str
    description: str
    workspace_path: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    workspace_path: str | None
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class TaskTransitionRequest(BaseModel):
    to_status: TaskStatus
    message: str | None = None
    created_by: str = "human_supervisor"


class TaskRequirementUpdate(BaseModel):
    description: str
    created_by: str = "human_supervisor"


class TaskEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    event_type: str
    from_status: TaskStatus | None
    to_status: TaskStatus | None
    message: str | None
    created_by: str
    created_at: datetime


class TaskDetail(BaseModel):
    task: TaskRead
    events: list[TaskEventRead]
