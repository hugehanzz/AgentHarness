from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.gemini import GeminiTaskBrief, GeminiTaskFacts, GeminiTestRequest, GeminiTextResponse
from app.services.gemini_brief_service import generate_gemini_task_brief
from app.services.gemini_facts_service import build_gemini_task_facts
from app.services.gemini_service import generate_gemini_text

router = APIRouter(prefix="/gemini", tags=["gemini"])


@router.post("/test", response_model=GeminiTextResponse)
async def test_gemini(payload: GeminiTestRequest):
    return await generate_gemini_text(payload.prompt)


@router.get("/tasks/{task_id}/facts", response_model=GeminiTaskFacts)
def task_facts(task_id: int, session: Session = Depends(get_session)):
    return build_gemini_task_facts(session, task_id)


@router.post("/tasks/{task_id}/brief", response_model=GeminiTaskBrief)
async def task_brief(task_id: int, session: Session = Depends(get_session)):
    facts = build_gemini_task_facts(session, task_id)
    return await generate_gemini_task_brief(facts)
