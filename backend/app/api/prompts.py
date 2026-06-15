from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.prompt import PromptCreateRequest, PromptRead
from app.services.prompt_service import create_prompt

router = APIRouter(prefix="/tasks/{task_id}/prompts", tags=["prompts"])


@router.post("", response_model=PromptRead)
def create(task_id: int, payload: PromptCreateRequest, session: Session = Depends(get_session)):
    return create_prompt(session, task_id, payload.prompt_type)
