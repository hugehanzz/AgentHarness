from pydantic import BaseModel

from app.models.prompt import PromptType


class PromptPreviewRead(BaseModel):
    task_id: int
    prompt_type: PromptType
    content: str
