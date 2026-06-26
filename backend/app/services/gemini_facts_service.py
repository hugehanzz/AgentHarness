import hashlib
import json

from sqlmodel import Session

from app.core.state_machine import HUMAN_GATE_STATUSES, TaskStatus
from app.models.review import ReviewItem, ReviewItemStatus, ReviewSeverity
from app.schemas.gemini import (
    GeminiAgentRunFact,
    GeminiCommandRunFact,
    GeminiEventFact,
    GeminiGateFact,
    GeminiReviewSummary,
    GeminiTaskFact,
    GeminiTaskFacts,
    GeminiWorkflowGuidance,
)
from app.schemas.workflow import ResolvedWorkflowState
from app.services.task_context_service import load_task_context_snapshot
from app.services.workflow_action_service import resolve_task_workflow_snapshot


MAX_EXCERPT_LENGTH = 700

GATE_FACTS: dict[TaskStatus, GeminiGateFact] = {
    TaskStatus.PLAN_READY: GeminiGateFact(
        type="计划确认",
        owner="Human Supervisor",
        reason="Codex 已准备好实现计划，需要由 Human Supervisor 确认后才能开始开发。",
    ),
    TaskStatus.ACCEPTANCE_READY: GeminiGateFact(
        type="最终验收",
        owner="Human Supervisor",
        reason="任务已完成开发和质量检查，需要由 Human Supervisor 做最终验收决定。",
    ),
}

STATUS_GUIDANCE: dict[TaskStatus, tuple[str, str, str]] = {
    TaskStatus.REQUIREMENT_DRAFT: ("Requirement", "需求草稿", "需求已经创建，下一步需要请求 Codex 生成实现计划。"),
    TaskStatus.PLAN_REQUESTED: ("Plan", "正在请求计划", "任务已进入计划阶段，下一步需要运行 Codex Plan。"),
    TaskStatus.PLAN_READY: ("Plan", "计划待确认", "Codex 已产出计划，当前等待 Human Supervisor 确认。"),
    TaskStatus.PLAN_CONFIRMED: ("Plan", "计划已确认", "计划已经确认，下一步可以让 Codex 开始实现。"),
    TaskStatus.IMPLEMENTING: ("Build", "开发中", "Codex 正在或即将执行实现工作。"),
    TaskStatus.IMPLEMENT_DONE: ("Build", "开发完成", "实现已经完成，下一步需要让 Claude 进行代码评审。"),
    TaskStatus.REVIEW_REQUESTED: ("Review", "正在请求评审", "任务已进入评审阶段，下一步需要运行 Claude Review。"),
    TaskStatus.REVIEW_DONE: ("Review", "评审完成", "Claude 已完成评审，当前需要决定是要求修复，还是进入验收。"),
    TaskStatus.FIX_REQUIRED: ("Fix", "需要修复", "评审发现需要处理的问题，下一步应让 Codex 根据 REVIEW.md 修复。"),
    TaskStatus.FIXING: ("Fix", "修复中", "Codex 正在或即将修复评审问题。"),
    TaskStatus.FIX_DONE: ("Fix", "修复完成", "Codex 已完成修复，下一步需要让 Claude 复审。"),
    TaskStatus.RECHECK_REQUESTED: ("Recheck", "正在请求复审", "任务已进入复审阶段，下一步需要运行 Claude Recheck。"),
    TaskStatus.RECHECK_DONE: ("Recheck", "复审完成", "Claude 已完成复审，当前需要决定是继续修复，还是进入验收。"),
    TaskStatus.FINALIZE_REQUESTED: ("Accept", "等待审查封板", "任务已进入验收大阶段，下一步需要运行 Claude 审查封板。"),
    TaskStatus.ACCEPTANCE_READY: ("Accept", "待验收", "任务已经准备好进入人工验收。"),
    TaskStatus.ACCEPTANCE_PASSED: ("Accept", "验收通过", "Human Supervisor 已确认验收通过，下一步需要让 Codex 处理 README 归档。"),
    TaskStatus.ARCHIVED: ("Archive", "已归档", "Codex 已完成 README 归档检查，下一步可以标记任务完成。"),
    TaskStatus.DONE: ("Done", "已完成", "任务已经结束，通常不需要继续操作。"),
}

def build_gemini_task_facts(session: Session, task_id: int) -> GeminiTaskFacts:
    snapshot = load_task_context_snapshot(session, task_id)
    task = snapshot.task
    workflow_state = resolve_task_workflow_snapshot(snapshot)

    # Gemini 接收只读的事实包，而不是直接的数据库或工作区访问。这让 Secretary 回答有据可依，同时不赋予它变更任务状态或外部项目文件的权限。
    payload = {
        "task": GeminiTaskFact(
            id=task.id,
            title=task.title,
            description=task.description,
            workspace_path=task.workspace_path,
            status=task.status,
            mode=task.mode,
        ),
        "current_gate": get_current_gate(task.status),
        "workflow_guidance": build_workflow_guidance(task.status, workflow_state),
        "recent_events": [
            GeminiEventFact(
                event_type=event.event_type,
                from_status=event.from_status,
                to_status=event.to_status,
                message=event.message,
                created_by=event.created_by,
                created_at=event.created_at.isoformat(),
            )
            for event in snapshot.recent_events
        ],
        "latest_agent_runs": [
            GeminiAgentRunFact(
                id=run.id,
                run_type=run.run_type,
                provider_type=run.provider_type,
                status=run.status,
                output_excerpt=excerpt(run.output_payload),
                error_message=run.error_message,
                finished_at=run.finished_at.isoformat() if run.finished_at else None,
                created_at=run.created_at.isoformat(),
            )
            for run in snapshot.recent_agent_runs
        ],
        "review_summary": build_review_summary(snapshot.review_items),
        "recent_commands": [
            GeminiCommandRunFact(
                id=command.id,
                command_key=command.command_key,
                status=command.status,
                exit_code=command.exit_code,
                duration_ms=command.duration_ms,
                created_at=command.created_at.isoformat(),
            )
            for command in snapshot.recent_commands
        ],
    }

    return GeminiTaskFacts(
        facts_version=build_facts_version(payload),
        **payload,
    )


def build_facts_version(payload: dict) -> str:
    # 前端使用此稳定哈希来决定缓存的 Gemini brief 在任务事件、runs、reviews 或命令结果更改后是否仍然有效。
    stable_json = json.dumps(
        normalize_for_hash(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()


def normalize_for_hash(value):
    if hasattr(value, "model_dump"):
        return normalize_for_hash(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {key: normalize_for_hash(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]
    return value


def get_current_gate(status: TaskStatus) -> GeminiGateFact | None:
    if status not in HUMAN_GATE_STATUSES:
        return None
    return GATE_FACTS.get(status)


def build_workflow_guidance(
    status: TaskStatus,
    workflow_state: ResolvedWorkflowState,
) -> GeminiWorkflowGuidance:
    stage_label, status_label, position = STATUS_GUIDANCE[status]
    return GeminiWorkflowGuidance(
        current_stage_label=stage_label,
        current_status_label=status_label,
        current_position=f"{position} {workflow_state.activity.message}",
        activity=workflow_state.activity,
        available_user_actions=workflow_state.actions,
    )


def build_review_summary(items: list[ReviewItem]) -> GeminiReviewSummary:
    open_items = [item for item in items if item.status == ReviewItemStatus.OPEN]
    return GeminiReviewSummary(
        total_count=len(items),
        open_count=len(open_items),
        high_open_count=count_open_by_severity(open_items, ReviewSeverity.HIGH),
        medium_open_count=count_open_by_severity(open_items, ReviewSeverity.MEDIUM),
        low_open_count=count_open_by_severity(open_items, ReviewSeverity.LOW),
        unknown_open_count=count_open_by_severity(open_items, ReviewSeverity.UNKNOWN),
        open_items=[item.title for item in open_items[:5]],
    )


def count_open_by_severity(items: list[ReviewItem], severity: ReviewSeverity) -> int:
    return sum(1 for item in items if item.severity == severity)


def excerpt(value: str | None) -> str | None:
    if not value:
        return value
    normalized = value.strip()
    if len(normalized) <= MAX_EXCERPT_LENGTH:
        return normalized
    return f"{normalized[:MAX_EXCERPT_LENGTH].rstrip()}..."
