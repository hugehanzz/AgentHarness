from sqlmodel import Session

from app.models.prompt import PromptType
from app.prompts.templates import build_prompt
from app.services.task_service import get_task_or_404


def preview_prompt(session: Session, task_id: int, prompt_type: PromptType) -> str:
    task = get_task_or_404(session, task_id)
    return build_prompt(task, prompt_type)
