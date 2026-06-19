from datetime import datetime

from pydantic import BaseModel

from app.models.prompt import PromptType


class PromptCreateRequest(BaseModel):
    prompt_type: PromptType


class PromptRead(BaseModel):
    id: int
    task_id: int
    prompt_type: PromptType
    content: str
    created_at: datetime


class PromptPreviewRead(BaseModel):
    task_id: int
    prompt_type: PromptType
    content: str
