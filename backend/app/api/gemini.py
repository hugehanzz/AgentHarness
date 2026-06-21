from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.gemini import GeminiChatRequest, GeminiTaskBrief, GeminiTaskFacts, GeminiTestRequest, GeminiTextResponse
from app.services.gemini_brief_service import generate_gemini_task_brief
from app.services.gemini_chat_service import (
    build_home_chat_messages,
    build_task_chat_messages,
    stream_diagnostic_chat,
    stream_gemini_chat,
)
from app.services.gemini_facts_service import build_gemini_task_facts
from app.services.gemini_service import generate_gemini_text

router = APIRouter(prefix="/gemini", tags=["gemini"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/test", response_model=GeminiTextResponse)
async def test_gemini(payload: GeminiTestRequest):
    return await generate_gemini_text(payload.prompt)


@router.post("/chat/stream")
async def home_chat_stream(payload: GeminiChatRequest):
    return StreamingResponse(
        stream_gemini_chat(build_home_chat_messages(payload)),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/tasks/{task_id}/chat/stream")
async def task_chat_stream(task_id: int, payload: GeminiChatRequest, session: Session = Depends(get_session)):
    facts = build_gemini_task_facts(session, task_id)
    return StreamingResponse(
        stream_gemini_chat(build_task_chat_messages(facts, payload), facts.facts_version),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/chat/diagnostic-stream")
async def diagnostic_chat_stream():
    return StreamingResponse(
        stream_diagnostic_chat(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/tasks/{task_id}/facts", response_model=GeminiTaskFacts)
def task_facts(task_id: int, session: Session = Depends(get_session)):
    return build_gemini_task_facts(session, task_id)


@router.post("/tasks/{task_id}/brief", response_model=GeminiTaskBrief)
async def task_brief(task_id: int, session: Session = Depends(get_session)):
    facts = build_gemini_task_facts(session, task_id)
    return await generate_gemini_task_brief(facts)
