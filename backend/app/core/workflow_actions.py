from dataclasses import dataclass
from enum import StrEnum

from app.core.state_machine import TaskStatus


class AgentRunTiming(StrEnum):
    BEFORE_TRANSITION = "before_transition"
    AFTER_TRANSITION = "after_transition"


@dataclass(frozen=True)
class WorkflowActionDefinition:
    action_id: str
    from_status: TaskStatus
    to_status: TaskStatus
    label: str
    agent_run_type: str | None = None
    agent_run_timing: AgentRunTiming | None = None
    requires_human_gate: bool = False

    def __post_init__(self) -> None:
        if bool(self.agent_run_type) != bool(self.agent_run_timing):
            raise ValueError("agent_run_type and agent_run_timing must be configured together")


# This catalog is the product-level description of every workflow button.
# State-machine validation remains in state_machine.py; later consumers such as
# the task UI and Gemini facts should read button semantics from this catalog.
WORKFLOW_ACTIONS: tuple[WorkflowActionDefinition, ...] = (
    WorkflowActionDefinition(
        action_id="request_plan",
        from_status=TaskStatus.REQUIREMENT_DRAFT,
        to_status=TaskStatus.PLAN_REQUESTED,
        label="请求计划",
        agent_run_type="codex_plan",
        agent_run_timing=AgentRunTiming.AFTER_TRANSITION,
    ),
    WorkflowActionDefinition(
        action_id="mark_plan_ready",
        from_status=TaskStatus.PLAN_REQUESTED,
        to_status=TaskStatus.PLAN_READY,
        label="计划已准备",
    ),
    WorkflowActionDefinition(
        action_id="confirm_plan",
        from_status=TaskStatus.PLAN_READY,
        to_status=TaskStatus.PLAN_CONFIRMED,
        label="确认计划",
        requires_human_gate=True,
    ),
    WorkflowActionDefinition(
        action_id="start_development",
        from_status=TaskStatus.PLAN_CONFIRMED,
        to_status=TaskStatus.IMPLEMENTING,
        label="开始开发",
        agent_run_type="codex_implement",
        agent_run_timing=AgentRunTiming.AFTER_TRANSITION,
    ),
    WorkflowActionDefinition(
        action_id="mark_development_complete",
        from_status=TaskStatus.IMPLEMENTING,
        to_status=TaskStatus.IMPLEMENT_DONE,
        label="标记开发完成",
    ),
    WorkflowActionDefinition(
        action_id="request_review",
        from_status=TaskStatus.IMPLEMENT_DONE,
        to_status=TaskStatus.REVIEW_REQUESTED,
        label="请求评审",
        agent_run_type="claude_review",
        agent_run_timing=AgentRunTiming.AFTER_TRANSITION,
    ),
    WorkflowActionDefinition(
        action_id="mark_review_complete",
        from_status=TaskStatus.REVIEW_REQUESTED,
        to_status=TaskStatus.REVIEW_DONE,
        label="标记评审完成",
    ),
    WorkflowActionDefinition(
        action_id="request_fix_after_review",
        from_status=TaskStatus.REVIEW_DONE,
        to_status=TaskStatus.FIX_REQUIRED,
        label="要求修复",
    ),
    WorkflowActionDefinition(
        action_id="enter_acceptance_after_review",
        from_status=TaskStatus.REVIEW_DONE,
        to_status=TaskStatus.ACCEPTANCE_READY,
        label="进入验收",
        agent_run_type="claude_recheck",
        agent_run_timing=AgentRunTiming.BEFORE_TRANSITION,
    ),
    WorkflowActionDefinition(
        action_id="start_fix",
        from_status=TaskStatus.FIX_REQUIRED,
        to_status=TaskStatus.FIXING,
        label="开始修复",
        agent_run_type="codex_fix",
        agent_run_timing=AgentRunTiming.AFTER_TRANSITION,
    ),
    WorkflowActionDefinition(
        action_id="mark_fix_complete",
        from_status=TaskStatus.FIXING,
        to_status=TaskStatus.FIX_DONE,
        label="标记修复完成",
    ),
    WorkflowActionDefinition(
        action_id="request_recheck",
        from_status=TaskStatus.FIX_DONE,
        to_status=TaskStatus.RECHECK_REQUESTED,
        label="请求复审",
        agent_run_type="claude_recheck",
        agent_run_timing=AgentRunTiming.AFTER_TRANSITION,
    ),
    WorkflowActionDefinition(
        action_id="mark_recheck_complete",
        from_status=TaskStatus.RECHECK_REQUESTED,
        to_status=TaskStatus.RECHECK_DONE,
        label="标记复审完成",
    ),
    WorkflowActionDefinition(
        action_id="request_fix_after_recheck",
        from_status=TaskStatus.RECHECK_DONE,
        to_status=TaskStatus.FIX_REQUIRED,
        label="要求修复",
    ),
    WorkflowActionDefinition(
        action_id="enter_acceptance_after_recheck",
        from_status=TaskStatus.RECHECK_DONE,
        to_status=TaskStatus.ACCEPTANCE_READY,
        label="进入验收",
    ),
    WorkflowActionDefinition(
        action_id="mark_acceptance_passed",
        from_status=TaskStatus.ACCEPTANCE_READY,
        to_status=TaskStatus.ACCEPTANCE_PASSED,
        label="标记验收通过",
        requires_human_gate=True,
    ),
    WorkflowActionDefinition(
        action_id="archive_task",
        from_status=TaskStatus.ACCEPTANCE_PASSED,
        to_status=TaskStatus.ARCHIVED,
        label="Codex 归档",
        agent_run_type="codex_archive",
        agent_run_timing=AgentRunTiming.AFTER_TRANSITION,
    ),
    WorkflowActionDefinition(
        action_id="mark_done",
        from_status=TaskStatus.ARCHIVED,
        to_status=TaskStatus.DONE,
        label="标记完成",
    ),
)


WORKFLOW_ACTION_BY_TRANSITION = {
    (action.from_status, action.to_status): action
    for action in WORKFLOW_ACTIONS
}


def get_workflow_actions(status: TaskStatus) -> tuple[WorkflowActionDefinition, ...]:
    return tuple(action for action in WORKFLOW_ACTIONS if action.from_status == status)


def get_workflow_action(
    from_status: TaskStatus,
    to_status: TaskStatus,
) -> WorkflowActionDefinition | None:
    return WORKFLOW_ACTION_BY_TRANSITION.get((from_status, to_status))
