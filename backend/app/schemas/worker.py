from datetime import datetime

from pydantic import BaseModel

from app.models.worker import WorkerStatus


class AgentWorkerRead(BaseModel):
    id: int
    worker_key: str
    name: str
    role: str
    provider_type: str
    status: WorkerStatus
    last_heartbeat_at: datetime | None
