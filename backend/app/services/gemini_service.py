import asyncio
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
import httpx

from app.core.config import get_settings
from app.schemas.gemini import GeminiTextResponse


def build_gemini_native_model_url(base_url: str, model: str, action: str) -> str:
    normalized_model = model.removeprefix("models/")
    return f"{base_url.rstrip('/')}/v1beta/models/{quote(normalized_model, safe='')}:{action}"


def resolve_gemini_base_url(gemini_base_url: str, google_gemini_base_url: str | None = None) -> str:
    return (google_gemini_base_url or gemini_base_url).rstrip("/")


def build_gemini_native_payload(prompt: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        },
    }


def extract_native_text(payload: dict[str, Any]) -> tuple[str, str | None]:
    texts: list[str] = []
    finish_reason: str | None = None
    for candidate in payload.get("candidates", []):
        if isinstance(candidate.get("finishReason"), str):
            finish_reason = candidate["finishReason"]
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)

    text = "".join(texts).strip()
    if not text:
        raise HTTPException(status_code=502, detail="Gemini native response did not include text")
    return text, finish_reason


async def generate_gemini_text(prompt: str) -> GeminiTextResponse:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured")
    base_url = resolve_gemini_base_url(
        settings.gemini_base_url,
        settings.google_gemini_base_url,
    )

    try:
        async with httpx.AsyncClient(proxy=settings.gemini_proxy_url, timeout=settings.gemini_timeout_seconds) as client:
            response = await client.post(
                build_gemini_native_model_url(base_url, settings.gemini_model, "generateContent"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": settings.gemini_api_key,
                },
                json=build_gemini_native_payload(prompt),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Gemini native API returned {response.status_code}: {response.text}",
            )
    except TimeoutError as exc:
        raise HTTPException(status_code=502, detail="Gemini native request timed out") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=502, detail=f"Gemini native API timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini native API request failed: {exc}") from exc

    text, finish_reason = extract_native_text(response.json())
    return GeminiTextResponse(
        ok=True,
        model=settings.gemini_model,
        text=text,
        finish_reason=finish_reason,
    )
