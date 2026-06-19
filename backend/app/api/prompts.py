from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.models.prompt import PromptType
from app.schemas.prompt import PromptCreateRequest, PromptPreviewRead, PromptRead
from app.services.prompt_service import create_prompt, preview_prompt

router = APIRouter(prefix="/tasks/{task_id}/prompts", tags=["prompts"])


@router.post("", response_model=PromptRead)
def create(task_id: int, payload: PromptCreateRequest, session: Session = Depends(get_session)):
    return create_prompt(session, task_id, payload.prompt_type)


@router.get("/preview", response_model=PromptPreviewRead)
def preview(task_id: int, prompt_type: PromptType, session: Session = Depends(get_session)):
    return PromptPreviewRead(
        task_id=task_id,
        prompt_type=prompt_type,
        content=preview_prompt(session, task_id, prompt_type),
    )
