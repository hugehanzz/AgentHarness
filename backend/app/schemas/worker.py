from datetime import datetime

from pydantic import BaseModel

from app.models.worker import WorkerRole, WorkerStatus


class AgentWorkerRead(BaseModel):
    id: int
    name: str
    role: WorkerRole
    worker_type: str
    status: WorkerStatus
    last_heartbeat_at: datetime | None
    current_task_id: int | None
    is_online: bool
