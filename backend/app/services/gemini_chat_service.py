import asyncio
import json
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
import httpx

from app.core.config import get_settings
from app.schemas.gemini import GeminiChatRequest, GeminiTaskFacts
from app.services.gemini_context_service import build_gemini_task_context
from app.services.gemini_service import resolve_gemini_base_url
from app.services.gemini_worker_service import (
    begin_gemini_request,
    finish_gemini_request,
    maintain_gemini_heartbeat,
    mark_gemini_offline,
    stop_gemini_heartbeat,
)

DELTA_CHUNK_SIZE = 8
DELTA_CHUNK_DELAY_SECONDS = 0.025


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def split_text_delta(text: str, chunk_size: int = DELTA_CHUNK_SIZE) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text else []
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


async def stream_text_delta(text: str):
    # Gemini 有时在长时间的首 token 等待后发送大的原生 delta。
    # 在转发之前分割它，以便浏览器仍然绘制可读的流。
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
    context_json = json.dumps(
        build_gemini_task_context(facts),
        ensure_ascii=False,
        indent=2,
    )
    return [
        {
            "role": "system",
            "content": (
                "你是 AgentHarness 系统内的 Gemini 秘书。你正在任务详情页中和用户对话。"
                "只能基于下方 facts 回答当前任务状态、进度、风险、下一步建议。"
                "你不能确认计划、不能批准验收、不能安装依赖、不能绕过 Human Supervisor gate，"
                "也不能声称已经修改外部业务项目代码。默认用中文回答，保持简短，通常不超过 5 句话。"
                "如果用户要求回复固定文本、OK、收到、确认等短句，必须严格按用户要求回复，不要展开说明。\n\n"
                f"CURRENT_TASK_FACTS:\n{context_json}"
            ),
        },
        *normalize_history(payload),
        {"role": "user", "content": payload.message.strip()},
    ]


def build_native_stream_url(base_url: str, model: str) -> str:
    normalized_model = model.removeprefix("models/")
    return f"{base_url.rstrip('/')}/v1beta/models/{quote(normalized_model, safe='')}:streamGenerateContent"


def build_native_payload(messages: list[dict[str, str]]) -> dict[str, Any]:
    system_parts: list[dict[str, str]] = []
    contents: list[dict[str, Any]] = []

    # Gemini 原生聊天对 assistant 轮次使用 "model"，而 UI 和 OpenAI 风格的 history 使用 "assistant"。在 API 边缘保持映射。
    for message in messages:
        role = message["role"]
        content = message["content"]
        if role == "system":
            system_parts.append({"text": content})
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": content}],
            }
        )

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 512,
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}
    return payload


def normalize_history(payload: GeminiChatRequest) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in payload.history[-8:]:
        content = item.content.strip()
        if not content:
            continue
        normalized.append({"role": item.role, "content": content[:4000]})
    return normalized


def extract_native_stream_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for candidate in payload.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "".join(texts)


def parse_native_sse_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    data = line.removeprefix("data:").strip()
    if not data or data == "[DONE]":
        return None
    return json.loads(data)


async def stream_gemini_chat(messages: list[dict[str, str]], facts_version: str | None = None):
    settings = get_settings()
    if not settings.gemini_api_key:
        mark_gemini_offline()
        yield sse_event("error", {"detail": "GEMINI_API_KEY is not configured"})
        return

    begin_gemini_request()
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(maintain_gemini_heartbeat(heartbeat_stop))
    success = False
    try:
        base_url = resolve_gemini_base_url(
            settings.gemini_base_url,
            settings.google_gemini_base_url,
        )
        url = build_native_stream_url(base_url, settings.gemini_model)
        async with httpx.AsyncClient(proxy=settings.gemini_proxy_url, timeout=settings.gemini_timeout_seconds) as client:
            async with client.stream(
                "POST",
                url,
                params={"alt": "sse"},
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": settings.gemini_api_key,
                },
                json=build_native_payload(messages),
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode("utf-8", errors="replace")
                    yield sse_event("error", {"detail": f"Gemini native API returned {response.status_code}: {detail}"})
                    return

                # 原生端点流式传输 SSE 行。我们仅解析数据帧并重新发出更小的、前端稳定的 SSE 信封。
                async for line in response.aiter_lines():
                    payload = parse_native_sse_line(line)
                    if not payload:
                        continue
                    text = extract_native_stream_text(payload)
                    if text:
                        async for event in stream_text_delta(text):
                            yield event

        success = True
        yield sse_event("done", {"model": settings.gemini_model, "facts_version": facts_version})
    except TimeoutError:
        yield sse_event("error", {"detail": "Gemini native streaming request timed out"})
    except HTTPException as exc:
        yield sse_event("error", {"detail": exc.detail})
    except httpx.TimeoutException as exc:
        yield sse_event("error", {"detail": f"Gemini native API timed out: {exc}"})
    except httpx.HTTPError as exc:
        yield sse_event("error", {"detail": f"Gemini native API request failed: {exc}"})
    except json.JSONDecodeError as exc:
        yield sse_event("error", {"detail": f"Gemini native API returned invalid SSE JSON: {exc}"})
    finally:
        await stop_gemini_heartbeat(heartbeat_stop, heartbeat_task)
        finish_gemini_request(success=success)
