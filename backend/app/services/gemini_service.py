import asyncio
from typing import Any

from fastapi import HTTPException
import httpx
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI

from app.core.config import get_settings
from app.schemas.gemini import GeminiTextResponse


def build_gemini_openai_base_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/v1beta/openai/"


def resolve_gemini_base_url(proxy_url: str | None, google_gemini_base_url: str | None, gemini_openai_base_url: str) -> str:
    if proxy_url:
        return gemini_openai_base_url
    if not google_gemini_base_url:
        raise HTTPException(status_code=400, detail="GOOGLE_GEMINI_BASE_URL is not configured")
    return google_gemini_base_url


def build_gemini_client(base_url: str, api_key: str, timeout_seconds: int, proxy_url: str | None = None) -> OpenAI:
    http_client = httpx.Client(proxy=proxy_url, timeout=timeout_seconds) if proxy_url else None
    return OpenAI(
        api_key=api_key,
        base_url=build_gemini_openai_base_url(base_url),
        timeout=timeout_seconds,
        http_client=http_client,
    )


def extract_openai_text(response: Any) -> tuple[str, str | None]:
    choices = getattr(response, "choices", None)
    if not choices:
        raise HTTPException(status_code=502, detail="Gemini OpenAI-compatible response does not include choices")

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    text = (getattr(message, "content", None) or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="Gemini OpenAI-compatible response did not include text")

    finish_reason = getattr(first_choice, "finish_reason", None)
    return text, finish_reason if isinstance(finish_reason, str) else None


async def generate_gemini_text(prompt: str) -> GeminiTextResponse:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured")
    base_url = resolve_gemini_base_url(
        settings.gemini_proxy_url,
        settings.google_gemini_base_url,
        settings.gemini_openai_base_url,
    )

    try:
        client = build_gemini_client(
            base_url,
            settings.gemini_api_key,
            settings.gemini_timeout_seconds,
            settings.gemini_proxy_url,
        )
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model=settings.gemini_model,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=settings.gemini_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=502, detail="Gemini OpenAI-compatible request timed out") from exc
    except APIStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini OpenAI-compatible API returned {exc.status_code}: {exc.response.text}",
        ) from exc
    except APITimeoutError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini OpenAI-compatible API timed out: {exc}") from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini OpenAI-compatible API connection failed: {exc}") from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini OpenAI-compatible API failed: {exc}") from exc

    text, finish_reason = extract_openai_text(response)
    return GeminiTextResponse(
        ok=True,
        model=settings.gemini_model,
        text=text,
        finish_reason=finish_reason,
    )
