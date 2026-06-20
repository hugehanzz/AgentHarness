from pydantic import BaseModel, Field


class GeminiTestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)


class GeminiTextResponse(BaseModel):
    ok: bool
    model: str
    text: str
    finish_reason: str | None = None
