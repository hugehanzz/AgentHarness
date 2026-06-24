import pytest
from fastapi import HTTPException

from app.core.state_machine import TaskStatus
from app.models.task import TaskMode
from app.schemas.gemini import (
    GeminiReviewSummary,
    GeminiTaskBrief,
    GeminiTaskFact,
    GeminiTaskFacts,
    GeminiTextResponse,
    GeminiWorkflowGuidance,
)
from app.schemas.workflow import WorkflowActivity, WorkflowActivityState
from app.schemas.workflow import ResolvedWorkflowAction
from app.services import gemini_brief_service
from app.services.gemini_brief_service import (
    build_gemini_brief_context,
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
        workflow_guidance=GeminiWorkflowGuidance(
            current_stage_label="Build",
            current_status_label="开发完成",
            current_position="实现已经完成，下一步需要让 Claude 进行代码评审。",
            activity=WorkflowActivity(
                state=WorkflowActivityState.WAITING_FOR_USER,
                message="当前流程正在等待用户执行下一步操作。",
            ),
            available_user_actions=[
                ResolvedWorkflowAction(
                    action_id="request_review",
                    label="请求评审",
                    from_status=TaskStatus.IMPLEMENT_DONE,
                    to_status=TaskStatus.REVIEW_REQUESTED,
                    enabled=True,
                    recommended=True,
                    instruction="点击「请求评审」继续当前流程。",
                    side_effects=["任务进入“评审中”状态", "随后运行 Claude 评审"],
                )
            ],
        ),
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
    )


def test_build_gemini_secretary_prompt_includes_facts_and_limits():
    prompt = build_gemini_secretary_prompt(make_facts())

    assert "只读 Gemini 秘书" in prompt
    assert "Gemini 不能代替人工批准" in prompt
    assert "请求评审" in prompt
    assert "IMPLEMENT_DONE" not in prompt
    assert "REVIEW_REQUESTED" not in prompt
    assert "只输出一个 JSON object" in prompt


def test_build_gemini_brief_context_omits_internal_workflow_protocol():
    context = build_gemini_brief_context(make_facts())
    serialized = str(context)

    assert context["workflow"]["status"] == "开发完成"
    assert context["actions"][0]["label"] == "请求评审"
    assert "action_id" not in serialized
    assert "to_status" not in serialized
    assert "IMPLEMENT_DONE" not in serialized
    assert "REVIEW_REQUESTED" not in serialized


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
        assert "CONTEXT" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-3.1-flash-lite",
            text="""{
  "summary": "当前任务已完成实现。",
  "current_position": "实现已经完成，正在等待发起评审。",
  "pending_gate": null,
  "suggested_next_steps": ["点击「请求评审」，让 Claude 检查当前实现。"],
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
    assert brief.suggested_next_steps == ["点击「请求评审」，让 Claude 检查当前实现。"]


def test_generate_gemini_task_brief_retries_invalid_button(monkeypatch):
    responses = iter(
        [
            """{
  "summary": "开发完成。",
  "current_position": "等待评审。",
  "pending_gate": null,
  "suggested_next_steps": ["点击「标记评审完成」"],
  "risk_notes": []
}""",
            """{
  "summary": "开发完成。",
  "current_position": "等待发起评审。",
  "pending_gate": null,
  "suggested_next_steps": ["点击「请求评审」"],
  "risk_notes": []
}""",
        ]
    )
    prompts: list[str] = []

    async def fake_generate(prompt: str):
        prompts.append(prompt)
        return GeminiTextResponse(
            ok=True,
            model="gemini-3.1-flash-lite",
            text=next(responses),
            finish_reason="stop",
        )

    monkeypatch.setattr(gemini_brief_service, "generate_gemini_text", fake_generate)

    import asyncio

    brief = asyncio.run(generate_gemini_task_brief(make_facts()))

    assert len(prompts) == 2
    assert "必须修正" in prompts[1]
    assert brief.suggested_next_steps == ["点击「请求评审」"]


def test_generate_gemini_task_brief_falls_back_after_repeated_invalid_output(monkeypatch):
    async def fake_generate(prompt: str):
        return GeminiTextResponse(
            ok=True,
            model="gemini-3.1-flash-lite",
            text="""{
  "summary": "当前是 IMPLEMENT_DONE。",
  "current_position": "等待 review。",
  "pending_gate": null,
  "suggested_next_steps": ["点击「标记评审完成」"],
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    monkeypatch.setattr(gemini_brief_service, "generate_gemini_text", fake_generate)

    import asyncio

    brief = asyncio.run(generate_gemini_task_brief(make_facts()))

    assert brief.summary == "任务当前处于“开发完成”状态。"
    assert brief.suggested_next_steps == ["点击「请求评审」继续当前流程。"]
    assert "IMPLEMENT_DONE" not in brief.summary


def test_validator_rejects_non_recommended_branch_when_recommendation_exists():
    facts = make_facts()
    facts.workflow_guidance.available_user_actions.append(
        ResolvedWorkflowAction(
            action_id="skip_review",
            label="直接验收",
            from_status=TaskStatus.IMPLEMENT_DONE,
            to_status=TaskStatus.ACCEPTANCE_READY,
            enabled=True,
            recommended=False,
            instruction="点击「直接验收」继续当前流程。",
        )
    )
    brief = GeminiTaskBrief(
        model="gemini",
        facts_version=facts.facts_version,
        summary="开发完成。",
        current_position="等待下一步操作。",
        pending_gate=None,
        suggested_next_steps=["点击「请求评审」", "也可以点击「直接验收」"],
        risk_notes=[],
    )

    errors = gemini_brief_service.validate_gemini_brief(brief, facts)

    assert any("不应同时建议点击「直接验收」" in error for error in errors)


def test_validator_rejects_premature_task_completion_claim():
    facts = make_facts()
    brief = GeminiTaskBrief(
        model="gemini",
        facts_version=facts.facts_version,
        summary="开发完成。",
        current_position="等待下一步操作。",
        pending_gate=None,
        suggested_next_steps=["点击「请求评审」以完成任务。"],
        risk_notes=[],
    )

    errors = gemini_brief_service.validate_gemini_brief(brief, facts)

    assert any("不会完成整个任务" in error for error in errors)
