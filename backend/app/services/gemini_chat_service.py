import asyncio
import json
from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError

from app.core.config import get_settings
from app.schemas.gemini import GeminiChatRequest, GeminiTaskFacts
from app.services.gemini_service import build_gemini_client, resolve_gemini_base_url

DELTA_CHUNK_SIZE = 8
DELTA_CHUNK_DELAY_SECONDS = 0.025


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def split_text_delta(text: str, chunk_size: int = DELTA_CHUNK_SIZE) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text else []
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


async def stream_text_delta(text: str):
    chunks = split_text_delta(text)
    for index, chunk in enumerate(chunks):
        yield sse_event("delta", {"text": chunk})
        if index < len(chunks) - 1:
            await asyncio.sleep(DELTA_CHUNK_DELAY_SECONDS)


async def stream_diagnostic_chat():
    for chunk in ["SSE ", "diagnostic ", "stream ", "is ", "working."]:
        yield sse_event("delta", {"text": chunk})
        await asyncio.sleep(0.35)
    yield sse_event("done", {"model": "diagnostic"})


def build_home_chat_messages(payload: GeminiChatRequest) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是 AgentHarness 系统内的 Gemini 秘书。你可以解释系统使用方式、回答用户问题、"
                "提醒用户查看任务详情，但不能确认计划、不能批准验收、不能安装依赖、不能绕过 Human Supervisor gate。"
                "默认用中文回答，保持简短，通常不超过 4 句话。"
                "如果用户要求回复固定文本、OK、收到、确认等短句，必须严格按用户要求回复，不要展开说明。"
            ),
        },
        *normalize_history(payload),
        {"role": "user", "content": payload.message.strip()},
    ]


def build_task_chat_messages(facts: GeminiTaskFacts, payload: GeminiChatRequest) -> list[dict[str, str]]:
    facts_json = facts.model_dump_json(indent=2)
    return [
        {
            "role": "system",
            "content": (
                "你是 AgentHarness 系统内的 Gemini 秘书。你正在任务详情页中和用户对话。"
                "只能基于下方 facts 回答当前任务状态、进度、风险、下一步建议。"
                "你不能确认计划、不能批准验收、不能安装依赖、不能绕过 Human Supervisor gate，"
                "也不能声称已经修改外部业务项目代码。默认用中文回答，保持简短，通常不超过 5 句话。"
                "如果用户要求回复固定文本、OK、收到、确认等短句，必须严格按用户要求回复，不要展开说明。\n\n"
                f"CURRENT_TASK_FACTS:\n{facts_json}"
            ),
        },
        *normalize_history(payload),
        {"role": "user", "content": payload.message.strip()},
    ]


def normalize_history(payload: GeminiChatRequest) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in payload.history[-8:]:
        content = item.content.strip()
        if not content:
            continue
        normalized.append({"role": item.role, "content": content[:4000]})
    return normalized


def extract_stream_delta(chunk: Any) -> str:
    choices = getattr(chunk, "choices", None)
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    content = getattr(delta, "content", None)
    return content if isinstance(content, str) else ""


def next_chunk(iterator: Iterator[Any]) -> Any | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


async def stream_gemini_chat(messages: list[dict[str, str]], facts_version: str | None = None):
    settings = get_settings()
    if not settings.gemini_api_key:
        yield sse_event("error", {"detail": "GEMINI_API_KEY is not configured"})
        return

    try:
        base_url = resolve_gemini_base_url(
            settings.gemini_proxy_url,
            settings.google_gemini_base_url,
            settings.gemini_openai_base_url,
        )
        client = build_gemini_client(
            base_url,
            settings.gemini_api_key,
            settings.gemini_timeout_seconds,
            settings.gemini_proxy_url,
        )
        iterator = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model=settings.gemini_model,
                messages=messages,
                max_tokens=512,
                temperature=0.2,
                stream=True,
            ),
            timeout=settings.gemini_timeout_seconds,
        )

        while True:
            chunk = await asyncio.wait_for(
                asyncio.to_thread(next_chunk, iterator),
                timeout=settings.gemini_timeout_seconds,
            )
            if chunk is None:
                break
            text = extract_stream_delta(chunk)
            if text:
                async for event in stream_text_delta(text):
                    yield event

        yield sse_event("done", {"model": settings.gemini_model, "facts_version": facts_version})
    except TimeoutError:
        yield sse_event("error", {"detail": "Gemini OpenAI-compatible streaming request timed out"})
    except HTTPException as exc:
        yield sse_event("error", {"detail": exc.detail})
    except APIStatusError as exc:
        yield sse_event(
            "error",
            {"detail": f"Gemini OpenAI-compatible API returned {exc.status_code}: {exc.response.text}"},
        )
    except APITimeoutError as exc:
        yield sse_event("error", {"detail": f"Gemini OpenAI-compatible API timed out: {exc}"})
    except APIConnectionError as exc:
        yield sse_event("error", {"detail": f"Gemini OpenAI-compatible API connection failed: {exc}"})
    except APIError as exc:
        yield sse_event("error", {"detail": f"Gemini OpenAI-compatible API failed: {exc}"})
