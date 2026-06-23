import pytest
from fastapi import HTTPException

from app.core.state_machine import TaskStatus
from app.models.task import TaskMode
from app.schemas.gemini import (
    GeminiReviewSummary,
    GeminiTaskFact,
    GeminiTaskFacts,
    GeminiTextResponse,
)
from app.services import gemini_brief_service
from app.services.gemini_brief_service import (
    build_gemini_secretary_prompt,
    generate_gemini_task_brief,
    parse_gemini_brief_json,
)


def make_facts() -> GeminiTaskFacts:
    return GeminiTaskFacts(
        facts_version="facts-v1",
        task=GeminiTaskFact(
            id=1,
            title="Demo",
            description="Requirement",
            workspace_path="D:\\workspace",
            status=TaskStatus.IMPLEMENT_DONE,
            mode=TaskMode.SECRETARY,
        ),
        current_gate=None,
        allowed_next_statuses=[TaskStatus.REVIEW_REQUESTED],
        recent_events=[],
        latest_agent_runs=[],
        review_summary=GeminiReviewSummary(
            total_count=0,
            open_count=0,
            high_open_count=0,
            medium_open_count=0,
            low_open_count=0,
            unknown_open_count=0,
            open_items=[],
        ),
        recent_commands=[],
        safe_next_actions=[],
    )


def test_build_gemini_secretary_prompt_includes_facts_and_limits():
    prompt = build_gemini_secretary_prompt(make_facts())

    assert "Gemini Secretary" in prompt
    assert "你不能批准计划" in prompt
    assert "IMPLEMENT_DONE" in prompt
    assert "只输出一个 JSON object" in prompt


def test_parse_gemini_brief_json_accepts_json_fence():
    parsed = parse_gemini_brief_json(
        """```json
{
  "summary": "已完成实现",
  "current_position": "等待 review",
  "pending_gate": null,
  "suggested_next_steps": ["请求 review"],
  "risk_notes": ["不能自动推进"]
}
```"""
    )

    assert parsed["summary"] == "已完成实现"
    assert parsed["pending_gate"] is None


def test_parse_gemini_brief_json_rejects_plain_text():
    with pytest.raises(HTTPException) as exc_info:
        parse_gemini_brief_json("任务已经完成")

    assert exc_info.value.status_code == 502


def test_generate_gemini_task_brief_returns_structured_response(monkeypatch):
    async def fake_generate(prompt: str):
        assert "task facts" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-3.1-flash-lite",
            text="""{
  "summary": "当前任务已完成实现。",
  "current_position": "处于 IMPLEMENT_DONE，可请求 review。",
  "pending_gate": null,
  "suggested_next_steps": ["请求 Claude-DeepSeek review"],
  "risk_notes": ["Gemini 只提供建议，不推进状态"]
}""",
            finish_reason="stop",
        )

    monkeypatch.setattr(gemini_brief_service, "generate_gemini_text", fake_generate)

    import asyncio

    brief = asyncio.run(generate_gemini_task_brief(make_facts()))

    assert brief.ok is True
    assert brief.model == "gemini-3.1-flash-lite"
    assert brief.facts_version == "facts-v1"
    assert brief.summary == "当前任务已完成实现。"
    assert brief.pending_gate is None
    assert brief.suggested_next_steps == ["请求 Claude-DeepSeek review"]
