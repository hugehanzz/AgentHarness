import asyncio

import pytest
from fastapi import HTTPException

from app.core.state_machine import TaskStatus
from app.models.task import TaskMode
from app.schemas.coordinator import CoordinatorDecision
from app.schemas.gemini import (
    GeminiReviewSummary,
    GeminiTaskFact,
    GeminiTaskFacts,
    GeminiTextResponse,
    GeminiWorkflowGuidance,
)
from app.schemas.workflow import ResolvedWorkflowAction, WorkflowActivity, WorkflowActivityState
from app.services import coordinator_service
from app.services.coordinator_service import (
    build_coordinator_decision_context,
    generate_coordinator_decision,
    parse_coordinator_decision_json,
    safe_candidate_actions,
    validate_coordinator_decision,
)


def make_facts(
    mode: TaskMode = TaskMode.COORDINATOR,
    activity_state: WorkflowActivityState = WorkflowActivityState.WAITING_FOR_USER,
    has_gate: bool = False,
) -> GeminiTaskFacts:
    from app.schemas.gemini import GeminiGateFact

    return GeminiTaskFacts(
        facts_version="facts-v1",
        task=GeminiTaskFact(
            id=1,
            title="Demo",
            description="Requirement",
            workspace_path="D:\\workspace",
            status=TaskStatus.IMPLEMENT_DONE,
            mode=mode,
        ),
        current_gate=(
            GeminiGateFact(
                type="计划确认",
                owner="Human Supervisor",
                reason="等待人工确认。",
            )
            if has_gate
            else None
        ),
        workflow_guidance=GeminiWorkflowGuidance(
            current_stage_label="Build",
            current_status_label="开发完成",
            current_position="实现已经完成，下一步需要让 Claude 进行代码评审。",
            activity=WorkflowActivity(
                state=activity_state,
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
                    requires_human_gate=False,
                    instruction="点击「请求评审」继续当前流程。",
                    side_effects=["任务进入“评审中”状态", "随后运行 Claude 评审"],
                ),
                ResolvedWorkflowAction(
                    action_id="mark_acceptance_passed",
                    label="标记验收通过",
                    from_status=TaskStatus.ACCEPTANCE_READY,
                    to_status=TaskStatus.ACCEPTANCE_PASSED,
                    enabled=True,
                    recommended=False,
                    requires_human_gate=True,
                    instruction="请由 Human Supervisor 核对当前结果。",
                    side_effects=["任务进入“验收通过”状态"],
                ),
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


def test_safe_candidate_actions_only_returns_enabled_non_gate_actions_for_coordinator_tasks():
    candidates = safe_candidate_actions(make_facts())

    assert [action.action_id for action in candidates] == ["request_review"]


def test_safe_candidate_actions_excludes_secretary_mode_and_human_gate():
    assert safe_candidate_actions(make_facts(mode=TaskMode.SECRETARY)) == []
    assert safe_candidate_actions(make_facts(has_gate=True)) == []
    assert safe_candidate_actions(make_facts(activity_state=WorkflowActivityState.AGENT_RUNNING)) == []


def test_build_coordinator_decision_context_exposes_action_ids_for_machine_choice():
    context = build_coordinator_decision_context(make_facts())

    assert context["candidate_actions"][0]["action_id"] == "request_review"
    assert context["candidate_actions"][0]["label"] == "请求评审"
    assert context["blocked_actions"][0]["action_id"] == "mark_acceptance_passed"
    assert context["blocked_actions"][0]["requires_human_gate"] is True


def test_parse_coordinator_decision_json_accepts_json_fence():
    decision = parse_coordinator_decision_json(
        """```json
{
  "decision": "continue",
  "selected_action_id": "request_review",
  "confidence": "high",
  "reason": "开发已完成，可以请求评审。",
  "risk_notes": []
}
```"""
    )

    assert decision.decision == "continue"
    assert decision.selected_action_id == "request_review"


def test_parse_coordinator_decision_json_rejects_plain_text():
    with pytest.raises(HTTPException):
        parse_coordinator_decision_json("请求评审")


def test_validate_coordinator_decision_accepts_safe_candidate():
    decision = CoordinatorDecision(
        decision="continue",
        selected_action_id="request_review",
        confidence="high",
        reason="开发已完成，可以请求评审。",
    )

    assert validate_coordinator_decision(decision, make_facts()) == []


def test_validate_coordinator_decision_rejects_illegal_action():
    decision = CoordinatorDecision(
        decision="continue",
        selected_action_id="confirm_plan",
        confidence="high",
        reason="尝试越过当前状态。",
    )

    errors = validate_coordinator_decision(decision, make_facts())

    assert any("不在安全候选动作" in error for error in errors)


def test_validate_coordinator_decision_rejects_continue_when_human_gate_exists():
    decision = CoordinatorDecision(
        decision="continue",
        selected_action_id="request_review",
        confidence="high",
        reason="尝试越过人工门禁。",
    )

    errors = validate_coordinator_decision(decision, make_facts(has_gate=True))

    assert any("Human Supervisor gate" in error for error in errors)
    assert any("不在安全候选动作" in error for error in errors)


def test_generate_coordinator_decision_returns_validation_errors(monkeypatch):
    async def fake_generate(prompt: str):
        assert "candidate_actions" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-test",
            text="""{
  "decision": "continue",
  "selected_action_id": "request_review",
  "confidence": "high",
  "reason": "开发已完成，可以请求评审。",
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fake_generate)

    result = asyncio.run(generate_coordinator_decision(make_facts()))

    assert result.model == "gemini-test"
    assert result.decision.selected_action_id == "request_review"
    assert result.validation_errors == []

