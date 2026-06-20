from fastapi import APIRouter

from app.schemas.gemini import GeminiTestRequest, GeminiTextResponse
from app.services.gemini_service import generate_gemini_text

router = APIRouter(prefix="/gemini", tags=["gemini"])


@router.post("/test", response_model=GeminiTextResponse)
async def test_gemini(payload: GeminiTestRequest):
    return await generate_gemini_text(payload.prompt)
