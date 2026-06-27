from sqlmodel import Session

from app.core.state_machine import HUMAN_GATE_STATUSES, TaskStatus
from app.core.workflow_actions import (
    AgentRunTiming,
    WorkflowActionDefinition,
    get_workflow_actions,
)
from app.models.review import ReviewItem, is_blocking_review_item_status
from app.models.worker import AgentRun, RunStatus
from app.schemas.workflow import (
    ResolvedWorkflowAction,
    ResolvedWorkflowState,
    WorkflowActionEvidence,
    WorkflowActivity,
    WorkflowActivityState,
)
from app.services.task_context_service import (
    WorkflowContextSnapshot,
    load_workflow_context_snapshot,
)


ACTIVE_AGENT_RUN_BY_STATUS: dict[TaskStatus, str] = {
    TaskStatus.PLAN_REQUESTED: "codex_plan",
    TaskStatus.IMPLEMENTING: "codex_implement",
    TaskStatus.REVIEW_REQUESTED: "claude_review",
    TaskStatus.FIXING: "codex_fix",
    TaskStatus.RECHECK_REQUESTED: "claude_recheck",
    TaskStatus.FINALIZE_REQUESTED: "claude_finalize",
    TaskStatus.ACCEPTANCE_READY: "codex_acceptance_checklist",
    TaskStatus.ARCHIVED: "codex_archive",
}

COMPLETION_EVIDENCE_BY_TRANSITION: dict[tuple[TaskStatus, TaskStatus], str] = {
    (TaskStatus.PLAN_REQUESTED, TaskStatus.PLAN_READY): "codex_plan",
    (TaskStatus.IMPLEMENTING, TaskStatus.IMPLEMENT_DONE): "codex_implement",
    (TaskStatus.REVIEW_REQUESTED, TaskStatus.REVIEW_DONE): "claude_review",
    (TaskStatus.FIXING, TaskStatus.FIX_DONE): "codex_fix",
    (TaskStatus.RECHECK_REQUESTED, TaskStatus.RECHECK_DONE): "claude_recheck",
    (TaskStatus.FINALIZE_REQUESTED, TaskStatus.ACCEPTANCE_READY): "claude_finalize",
    (TaskStatus.ACCEPTANCE_READY, TaskStatus.ACCEPTANCE_PASSED): "codex_acceptance_checklist",
    (TaskStatus.ARCHIVED, TaskStatus.DONE): "codex_archive",
}

RUN_LABELS: dict[str, str] = {
    "codex_plan": "Codex 计划",
    "codex_implement": "Codex 开发",
    "claude_review": "Claude 评审",
    "codex_fix": "Codex 修复",
    "claude_recheck": "Claude 复审",
    "claude_finalize": "Claude 审查封板",
    "codex_acceptance_checklist": "Codex 验收建议",
    "codex_archive": "Codex 归档",
}

STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.REQUIREMENT_DRAFT: "需求草稿",
    TaskStatus.PLAN_REQUESTED: "正在生成计划",
    TaskStatus.PLAN_READY: "计划待确认",
    TaskStatus.PLAN_CONFIRMED: "计划已确认",
    TaskStatus.IMPLEMENTING: "开发中",
    TaskStatus.IMPLEMENT_DONE: "开发完成",
    TaskStatus.REVIEW_REQUESTED: "评审中",
    TaskStatus.REVIEW_DONE: "评审完成",
    TaskStatus.FIX_REQUIRED: "等待修复",
    TaskStatus.FIXING: "修复中",
    TaskStatus.FIX_DONE: "修复完成",
    TaskStatus.RECHECK_REQUESTED: "复审中",
    TaskStatus.RECHECK_DONE: "复审完成",
    TaskStatus.FINALIZE_REQUESTED: "等待审查封板",
    TaskStatus.ACCEPTANCE_READY: "等待人工验收",
    TaskStatus.ACCEPTANCE_PASSED: "验收通过",
    TaskStatus.ARCHIVED: "归档完成",
    TaskStatus.DONE: "任务完成",
}


def resolve_task_workflow(session: Session, task_id: int) -> ResolvedWorkflowState:
    return resolve_task_workflow_snapshot(
        load_workflow_context_snapshot(session, task_id)
    )


def resolve_task_workflow_snapshot(
    snapshot: WorkflowContextSnapshot,
) -> ResolvedWorkflowState:
    task = snapshot.task
    actions = [
        resolve_action(
            action,
            snapshot.current_status_agent_runs,
            snapshot.review_items,
        )
        for action in get_workflow_actions(task.status)
    ]
    return ResolvedWorkflowState(
        task_id=task.id,
        current_status=task.status,
        activity=resolve_activity(task.status, snapshot.current_status_agent_runs),
        actions=actions,
    )


def resolve_action(
    definition: WorkflowActionDefinition,
    agent_runs: list[AgentRun],
    review_items: list[ReviewItem],
) -> ResolvedWorkflowAction:
    required_run_type = COMPLETION_EVIDENCE_BY_TRANSITION.get(
        (definition.from_status, definition.to_status)
    )
    needs_preexisting_evidence = not (
        required_run_type
        and definition.agent_run_type == required_run_type
        and definition.agent_run_timing == AgentRunTiming.BEFORE_TRANSITION
    )
    evidence = (
        build_evidence(required_run_type, agent_runs)
        if required_run_type and needs_preexisting_evidence
        else None
    )
    enabled = evidence is None or evidence.satisfied
    blocked_reason = None
    if evidence and not evidence.satisfied:
        blocked_reason = build_evidence_blocked_reason(evidence)

    recommended = (
        enabled
        and not definition.requires_human_gate
        and is_recommended_action(definition, review_items)
    )
    return ResolvedWorkflowAction(
        action_id=definition.action_id,
        label=definition.label,
        from_status=definition.from_status,
        to_status=definition.to_status,
        enabled=enabled,
        recommended=recommended,
        requires_human_gate=definition.requires_human_gate,
        agent_run_type=definition.agent_run_type,
        agent_run_timing=definition.agent_run_timing,
        instruction=build_instruction(definition, enabled, blocked_reason),
        side_effects=build_side_effects(definition),
        blocked_reason=blocked_reason,
        evidence=evidence,
    )


def build_evidence(required_run_type: str, agent_runs: list[AgentRun]) -> WorkflowActionEvidence:
    latest_run = next((run for run in agent_runs if run.run_type == required_run_type), None)
    return WorkflowActionEvidence(
        required_run_type=required_run_type,
        latest_run_status=latest_run.status if latest_run else None,
        latest_run_id=latest_run.id if latest_run else None,
        satisfied=latest_run is not None and latest_run.status == RunStatus.SUCCEEDED,
    )


def build_evidence_blocked_reason(evidence: WorkflowActionEvidence) -> str:
    run_label = RUN_LABELS.get(evidence.required_run_type, evidence.required_run_type)
    if evidence.latest_run_status in {RunStatus.QUEUED, RunStatus.RUNNING}:
        return f"{run_label}正在运行，请等待运行成功后再继续。"
    if evidence.latest_run_status in {RunStatus.FAILED, RunStatus.TIMED_OUT}:
        return f"{run_label}未成功完成，请查看 Agent Runs 并重新运行。"
    return f"请先运行并成功完成{run_label}。"


def is_recommended_action(
    definition: WorkflowActionDefinition,
    review_items: list[ReviewItem],
) -> bool:
    open_items = [item for item in review_items if is_blocking_review_item_status(item.status)]
    if definition.from_status in {TaskStatus.REVIEW_DONE, TaskStatus.RECHECK_DONE}:
        if definition.to_status == TaskStatus.FIX_REQUIRED:
            return bool(open_items)
        if definition.to_status == TaskStatus.FINALIZE_REQUESTED:
            return not open_items
    return True


def build_instruction(
    definition: WorkflowActionDefinition,
    enabled: bool,
    blocked_reason: str | None,
) -> str:
    if not enabled:
        return blocked_reason or f"当前还不能点击「{definition.label}」。"
    if definition.requires_human_gate:
        return f"请由 Human Supervisor 核对当前结果，确认无误后点击「{definition.label}」。"
    return f"点击「{definition.label}」继续当前流程。"


def build_side_effects(definition: WorkflowActionDefinition) -> list[str]:
    effects: list[str] = []
    if definition.agent_run_type and definition.agent_run_timing == AgentRunTiming.BEFORE_TRANSITION:
        effects.append(f"先运行{RUN_LABELS.get(definition.agent_run_type, definition.agent_run_type)}")
    effects.append(f"任务进入“{STATUS_LABELS[definition.to_status]}”状态")
    if definition.agent_run_type and definition.agent_run_timing == AgentRunTiming.AFTER_TRANSITION:
        effects.append(f"随后运行{RUN_LABELS.get(definition.agent_run_type, definition.agent_run_type)}")
    return effects


def resolve_activity(
    status: TaskStatus,
    agent_runs: list[AgentRun],
) -> WorkflowActivity:
    if status == TaskStatus.DONE:
        return WorkflowActivity(
            state=WorkflowActivityState.COMPLETED,
            message="任务流程已经完成。",
        )

    active_run_type = ACTIVE_AGENT_RUN_BY_STATUS.get(status)
    latest_run = next(
        (run for run in agent_runs if run.run_type == active_run_type),
        None,
    ) if active_run_type else None
    if latest_run:
        run_label = RUN_LABELS.get(latest_run.run_type, latest_run.run_type)
        if latest_run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            return WorkflowActivity(
                state=WorkflowActivityState.AGENT_RUNNING,
                message=f"{run_label}正在运行。",
                agent_run_type=latest_run.run_type,
                run_status=latest_run.status,
                run_id=latest_run.id,
            )
        if latest_run.status == RunStatus.SUCCEEDED:
            if status in HUMAN_GATE_STATUSES:
                return WorkflowActivity(
                    state=WorkflowActivityState.WAITING_FOR_HUMAN_GATE,
                    message=f"{run_label}已经成功完成，当前等待 Human Supervisor 确认。",
                    agent_run_type=latest_run.run_type,
                    run_status=latest_run.status,
                    run_id=latest_run.id,
                )
            return WorkflowActivity(
                state=WorkflowActivityState.AGENT_SUCCEEDED,
                message=f"{run_label}已经成功完成，等待用户确认下一步。",
                agent_run_type=latest_run.run_type,
                run_status=latest_run.status,
                run_id=latest_run.id,
            )
        return WorkflowActivity(
            state=WorkflowActivityState.AGENT_FAILED,
            message=f"{run_label}未成功完成，请查看 Agent Runs。",
            agent_run_type=latest_run.run_type,
            run_status=latest_run.status,
            run_id=latest_run.id,
        )

    if status in HUMAN_GATE_STATUSES:
        return WorkflowActivity(
            state=WorkflowActivityState.WAITING_FOR_HUMAN_GATE,
            message="当前流程正在等待 Human Supervisor 确认。",
            agent_run_type=active_run_type,
        )
    return WorkflowActivity(
        state=WorkflowActivityState.WAITING_FOR_USER,
        message="当前流程正在等待用户执行下一步操作。",
        agent_run_type=active_run_type,
    )
