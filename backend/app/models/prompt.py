from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.models.common import utc_now


class PromptType(StrEnum):
    CODEX_PLAN = "CODEX_PLAN"
    CODEX_IMPLEMENT = "CODEX_IMPLEMENT"
    CLAUDE_REVIEW = "CLAUDE_REVIEW"
    CODEX_FIX = "CODEX_FIX"
    CLAUDE_RECHECK = "CLAUDE_RECHECK"
    ACCEPTANCE_CHECKLIST = "ACCEPTANCE_CHECKLIST"
    README_ARCHIVE = "README_ARCHIVE"


class PromptRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="task.id")
    prompt_type: PromptType = Field(index=True)
    content: str
    created_at: datetime = Field(default_factory=utc_now)
