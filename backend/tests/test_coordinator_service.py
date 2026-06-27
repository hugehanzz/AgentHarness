import asyncio

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.state_machine import TaskStatus
from app.models.task import TaskMode
from app.models.worker import AgentRun, RunStatus
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
    run_coordinator_step,
    run_coordinator_until_blocked,
    safe_candidate_actions,
    validate_coordinator_action_selection,
    validate_coordinator_decision,
)
from app.schemas.task import TaskCreate
from app.services.task_service import create_task


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


def test_validate_coordinator_action_selection_accepts_safe_action():
    result = validate_coordinator_action_selection(make_facts(), "request_review")

    assert result.allowed is True
    assert result.action is not None
    assert result.action.action_id == "request_review"
    assert result.errors == []


def test_validate_coordinator_decision_rejects_illegal_action():
    decision = CoordinatorDecision(
        decision="continue",
        selected_action_id="confirm_plan",
        confidence="high",
        reason="尝试越过当前状态。",
    )

    errors = validate_coordinator_decision(decision, make_facts())

    assert any("不属于当前状态" in error for error in errors)


def test_validate_coordinator_decision_rejects_continue_when_human_gate_exists():
    decision = CoordinatorDecision(
        decision="continue",
        selected_action_id="request_review",
        confidence="high",
        reason="尝试越过人工门禁。",
    )

    errors = validate_coordinator_decision(decision, make_facts(has_gate=True))

    assert any("Human Supervisor gate" in error for error in errors)


def test_validate_coordinator_action_selection_rejects_disabled_action():
    facts = make_facts()
    facts.workflow_guidance.available_user_actions[0].enabled = False
    facts.workflow_guidance.available_user_actions[0].blocked_reason = "请先运行 Claude 评审。"

    result = validate_coordinator_action_selection(facts, "request_review")

    assert result.allowed is False
    assert result.action is None
    assert any("未启用" in error for error in result.errors)
    assert any("请先运行 Claude 评审" in error for error in result.errors)


def test_validate_coordinator_action_selection_rejects_human_gate_action():
    result = validate_coordinator_action_selection(make_facts(), "mark_acceptance_passed")

    assert result.allowed is False
    assert result.action is None
    assert any("需要 Human Supervisor" in error for error in result.errors)


def test_validate_coordinator_action_selection_rejects_secretary_mode():
    result = validate_coordinator_action_selection(make_facts(mode=TaskMode.SECRETARY), "request_review")

    assert result.allowed is False
    assert any("不是 Coordinator 模式" in error for error in result.errors)


def test_validate_coordinator_action_selection_rejects_running_agent():
    result = validate_coordinator_action_selection(
        make_facts(activity_state=WorkflowActivityState.AGENT_RUNNING),
        "request_review",
    )

    assert result.allowed is False
    assert any("已有 Agent 正在运行" in error for error in result.errors)


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


def create_memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_run_coordinator_step_stops_before_gemini_for_secretary_mode(monkeypatch):
    async def fail_generate(*args, **kwargs):
        raise AssertionError("Gemini should not be called for secretary mode")

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fail_generate)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Secretary", description="Requirement", mode=TaskMode.SECRETARY),
        )

        result = asyncio.run(run_coordinator_step(session, task.id))

        assert result.executed is False
        assert result.task_status_before == TaskStatus.REQUIREMENT_DRAFT
        assert result.task_status_after == TaskStatus.REQUIREMENT_DRAFT
        assert "不是 Coordinator 模式" in result.stop_reason


def test_run_coordinator_step_stops_at_human_gate(monkeypatch):
    async def fail_generate(*args, **kwargs):
        raise AssertionError("Gemini should not be called for human gate")

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fail_generate)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Plan", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.PLAN_READY
        session.add(task)
        session.commit()

        result = asyncio.run(run_coordinator_step(session, task.id))

        assert result.executed is False
        assert result.task_status_before == TaskStatus.PLAN_READY
        assert result.task_status_after == TaskStatus.PLAN_READY
        assert "Human Supervisor" in result.stop_reason


def test_run_coordinator_step_stops_cleanly_when_task_is_done(monkeypatch):
    async def fail_generate(*args, **kwargs):
        raise AssertionError("Gemini should not be called after task is done")

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fail_generate)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Done", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.DONE
        session.add(task)
        session.commit()

        result = asyncio.run(run_coordinator_step(session, task.id))

        assert result.executed is False
        assert result.task_status_before == TaskStatus.DONE
        assert result.task_status_after == TaskStatus.DONE
        assert result.stop_reason == "任务流程已经完成。"


def test_run_coordinator_step_rejects_gemini_illegal_action(monkeypatch):
    async def fake_generate(prompt: str):
        return GeminiTextResponse(
            ok=True,
            model="gemini-test",
            text="""{
  "decision": "continue",
  "selected_action_id": "confirm_plan",
  "confidence": "high",
  "reason": "错误地尝试确认计划。",
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fake_generate)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Build", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.IMPLEMENT_DONE
        session.add(task)
        session.commit()

        result = asyncio.run(run_coordinator_step(session, task.id))

        assert result.executed is False
        assert result.task_status_before == TaskStatus.IMPLEMENT_DONE
        assert result.task_status_after == TaskStatus.IMPLEMENT_DONE
        assert result.validation_errors
        assert any("不属于当前状态" in error for error in result.validation_errors)


def test_run_coordinator_step_executes_transition_without_agent(monkeypatch):
    async def fake_generate(prompt: str):
        assert "mark_development_complete" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-test",
            text="""{
  "decision": "continue",
  "selected_action_id": "mark_development_complete",
  "confidence": "high",
  "reason": "Codex 开发已成功完成，可以标记开发完成。",
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fake_generate)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Implementing", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.IMPLEMENTING
        session.add(task)
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="codex_implement",
                provider_type="codex_app_server",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()

        result = asyncio.run(run_coordinator_step(session, task.id))

        assert result.executed is True
        assert result.action_id == "mark_development_complete"
        assert result.task_status_before == TaskStatus.IMPLEMENTING
        assert result.task_status_after == TaskStatus.IMPLEMENT_DONE
        assert result.agent_run_id is None


def test_run_coordinator_step_executes_after_transition_agent_run(monkeypatch):
    async def fake_generate(prompt: str):
        assert "request_review" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-test",
            text="""{
  "decision": "continue",
  "selected_action_id": "request_review",
  "confidence": "high",
  "reason": "开发已完成，可以请求 Claude 评审。",
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    async def fake_run_agent(session: Session, task_id: int, run_type: str, prompt_override=None):
        task = session.get(app.models.Task, task_id)
        assert task.status == TaskStatus.REVIEW_REQUESTED
        run = AgentRun(
            task_id=task_id,
            run_type=run_type,
            provider_type="claude_cli",
            status=RunStatus.SUCCEEDED,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fake_generate)
    monkeypatch.setattr(coordinator_service, "run_agent", fake_run_agent)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Build", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.IMPLEMENT_DONE
        session.add(task)
        session.commit()

        result = asyncio.run(run_coordinator_step(session, task.id))

        assert result.executed is True
        assert result.action_id == "request_review"
        assert result.task_status_before == TaskStatus.IMPLEMENT_DONE
        assert result.task_status_after == TaskStatus.REVIEW_REQUESTED
        assert result.agent_run_id is not None
        assert result.agent_run_status == RunStatus.SUCCEEDED


def test_run_coordinator_until_blocked_stops_at_next_human_gate(monkeypatch):
    async def fake_generate(prompt: str):
        assert "mark_plan_ready" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-test",
            text="""{
  "decision": "continue",
  "selected_action_id": "mark_plan_ready",
  "confidence": "high",
  "reason": "Codex 计划已成功完成，可以标记计划已准备。",
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fake_generate)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Plan", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.PLAN_REQUESTED
        session.add(task)
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="codex_plan",
                provider_type="codex_app_server",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()

        result = asyncio.run(run_coordinator_until_blocked(session, task.id, max_steps=5))

        assert result.executed_steps == 1
        assert len(result.steps) == 2
        assert result.steps[0].executed is True
        assert result.steps[0].action_id == "mark_plan_ready"
        assert result.steps[0].task_status_after == TaskStatus.PLAN_READY
        assert result.steps[1].executed is False
        assert "Human Supervisor" in result.stop_reason


def test_run_coordinator_until_blocked_runs_finalize_before_acceptance_gate(monkeypatch):
    async def fake_generate(prompt: str):
        assert "mark_finalize_complete" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-test",
            text="""{
  "decision": "continue",
  "selected_action_id": "mark_finalize_complete",
  "confidence": "high",
  "reason": "可以执行审查封板并进入人工验收。",
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    async def fake_run_agent(session: Session, task_id: int, run_type: str, prompt_override=None):
        task = session.get(app.models.Task, task_id)
        assert task.status == TaskStatus.FINALIZE_REQUESTED
        assert run_type == "claude_finalize"
        run = AgentRun(
            task_id=task_id,
            run_type=run_type,
            provider_type="claude_cli",
            status=RunStatus.SUCCEEDED,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fake_generate)
    monkeypatch.setattr(coordinator_service, "run_agent", fake_run_agent)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Finalize", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.FINALIZE_REQUESTED
        session.add(task)
        session.commit()

        result = asyncio.run(run_coordinator_until_blocked(session, task.id, max_steps=5))

        assert result.executed_steps == 1
        assert len(result.steps) == 2
        assert result.steps[0].executed is True
        assert result.steps[0].action_id == "mark_finalize_complete"
        assert result.steps[0].agent_run_status == RunStatus.SUCCEEDED
        assert result.steps[0].task_status_after == TaskStatus.ACCEPTANCE_READY
        assert result.steps[1].executed is False
        assert "Human Supervisor" in result.stop_reason


def test_run_coordinator_until_blocked_runs_acceptance_checklist_before_human_pass(monkeypatch):
    async def fail_generate(*args, **kwargs):
        raise AssertionError("Gemini should not be called before acceptance checklist is generated")

    async def fake_run_agent(session: Session, task_id: int, run_type: str, prompt_override=None):
        task = session.get(app.models.Task, task_id)
        assert task.status == TaskStatus.ACCEPTANCE_READY
        assert run_type == "codex_acceptance_checklist"
        run = AgentRun(
            task_id=task_id,
            run_type=run_type,
            provider_type="codex_app_server",
            status=RunStatus.SUCCEEDED,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fail_generate)
    monkeypatch.setattr(coordinator_service, "run_agent", fake_run_agent)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Acceptance", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.ACCEPTANCE_READY
        session.add(task)
        session.commit()

        result = asyncio.run(run_coordinator_until_blocked(session, task.id, max_steps=5))

        assert result.executed_steps == 1
        assert len(result.steps) == 1
        assert result.steps[0].executed is True
        assert result.steps[0].action_id == "codex_acceptance_checklist"
        assert result.steps[0].agent_run_status == RunStatus.SUCCEEDED
        assert result.steps[0].task_status_after == TaskStatus.ACCEPTANCE_READY
        assert "Human Supervisor" in result.stop_reason


def test_run_coordinator_until_blocked_stops_after_agent_failure(monkeypatch):
    async def fake_generate(prompt: str):
        assert "request_review" in prompt
        return GeminiTextResponse(
            ok=True,
            model="gemini-test",
            text="""{
  "decision": "continue",
  "selected_action_id": "request_review",
  "confidence": "high",
  "reason": "开发已完成，可以请求 Claude 评审。",
  "risk_notes": []
}""",
            finish_reason="stop",
        )

    async def fake_run_agent(session: Session, task_id: int, run_type: str, prompt_override=None):
        run = AgentRun(
            task_id=task_id,
            run_type=run_type,
            provider_type="claude_cli",
            status=RunStatus.FAILED,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run

    monkeypatch.setattr(coordinator_service, "generate_gemini_text", fake_generate)
    monkeypatch.setattr(coordinator_service, "run_agent", fake_run_agent)

    with create_memory_session() as session:
        task = create_task(
            session,
            TaskCreate(title="Build", description="Requirement", mode=TaskMode.COORDINATOR),
        )
        task.status = TaskStatus.IMPLEMENT_DONE
        session.add(task)
        session.commit()

        result = asyncio.run(run_coordinator_until_blocked(session, task.id, max_steps=5))

        assert result.executed_steps == 1
        assert len(result.steps) == 1
        assert result.steps[0].agent_run_status == RunStatus.FAILED
        assert "did not succeed" in result.stop_reason
