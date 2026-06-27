import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.state_machine import TaskStatus
from app.models.worker import AgentRun, RunStatus
from app.schemas.task import TaskCreate
from app.schemas.workflow import WorkflowActivityState
from app.services.gemini_facts_service import build_gemini_task_facts
from app.services.task_service import create_task


FLOW_MATRIX = [
    (TaskStatus.REQUIREMENT_DRAFT, None, {"请求计划"}, WorkflowActivityState.WAITING_FOR_USER),
    (TaskStatus.PLAN_REQUESTED, "codex_plan", {"计划已准备"}, WorkflowActivityState.AGENT_SUCCEEDED),
    (TaskStatus.PLAN_READY, None, {"确认计划"}, WorkflowActivityState.WAITING_FOR_HUMAN_GATE),
    (TaskStatus.PLAN_CONFIRMED, None, {"开始开发"}, WorkflowActivityState.WAITING_FOR_USER),
    (TaskStatus.IMPLEMENTING, "codex_implement", {"标记开发完成"}, WorkflowActivityState.AGENT_SUCCEEDED),
    (TaskStatus.IMPLEMENT_DONE, None, {"请求评审"}, WorkflowActivityState.WAITING_FOR_USER),
    (TaskStatus.REVIEW_REQUESTED, "claude_review", {"标记评审完成"}, WorkflowActivityState.AGENT_SUCCEEDED),
    (TaskStatus.REVIEW_DONE, None, {"要求修复", "进入验收"}, WorkflowActivityState.WAITING_FOR_USER),
    (TaskStatus.FIX_REQUIRED, None, {"开始修复"}, WorkflowActivityState.WAITING_FOR_USER),
    (TaskStatus.FIXING, "codex_fix", {"标记修复完成"}, WorkflowActivityState.AGENT_SUCCEEDED),
    (TaskStatus.FIX_DONE, None, {"请求复审"}, WorkflowActivityState.WAITING_FOR_USER),
    (TaskStatus.RECHECK_REQUESTED, "claude_recheck", {"标记复审完成"}, WorkflowActivityState.AGENT_SUCCEEDED),
    (TaskStatus.RECHECK_DONE, None, {"要求修复", "进入验收"}, WorkflowActivityState.WAITING_FOR_USER),
    (
        TaskStatus.FINALIZE_REQUESTED,
        "claude_finalize",
        {"审查封板"},
        WorkflowActivityState.AGENT_SUCCEEDED,
    ),
    (
        TaskStatus.ACCEPTANCE_READY,
        "codex_acceptance_checklist",
        {"标记验收通过"},
        WorkflowActivityState.WAITING_FOR_HUMAN_GATE,
    ),
    (TaskStatus.ACCEPTANCE_PASSED, None, {"Codex 归档"}, WorkflowActivityState.WAITING_FOR_USER),
    (TaskStatus.ARCHIVED, "codex_archive", {"标记完成"}, WorkflowActivityState.AGENT_SUCCEEDED),
    (TaskStatus.DONE, None, set(), WorkflowActivityState.COMPLETED),
]


@pytest.mark.parametrize(
    ("status", "successful_run_type", "expected_labels", "expected_activity"),
    FLOW_MATRIX,
)
def test_gemini_facts_cover_complete_flow_matrix(
    status,
    successful_run_type,
    expected_labels,
    expected_activity,
):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title=status.value, description="Requirement"))
        task.status = status
        session.add(task)
        if successful_run_type:
            session.add(
                AgentRun(
                    task_id=task.id,
                    run_type=successful_run_type,
                    provider_type="test",
                    status=RunStatus.SUCCEEDED,
                )
            )
        session.commit()

        facts = build_gemini_task_facts(session, task.id)
        actions = facts.workflow_guidance.available_user_actions

        assert facts.workflow_guidance.activity.state == expected_activity
        assert {action.label for action in actions} == expected_labels
        assert all(
            internal_status.value not in effect
            for action in actions
            for effect in action.side_effects
            for internal_status in TaskStatus
        )
        assert all(action.label and action.instruction for action in actions)
