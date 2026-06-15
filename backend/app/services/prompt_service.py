from sqlmodel import Session

from app.models.prompt import PromptRecord, PromptType
from app.prompts.templates import build_prompt
from app.services.task_service import get_task_or_404


def create_prompt(session: Session, task_id: int, prompt_type: PromptType) -> PromptRecord:
    task = get_task_or_404(session, task_id)
    record = PromptRecord(task_id=task_id, prompt_type=prompt_type, content=build_prompt(task, prompt_type))
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
