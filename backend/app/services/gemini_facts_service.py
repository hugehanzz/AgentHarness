import hashlib
import json

from sqlmodel import Session, select

from app.core.state_machine import ALLOWED_TRANSITIONS, HUMAN_GATE_STATUSES, TaskStatus
from app.models.command import CommandRun
from app.models.review import ReviewItem, ReviewItemStatus, ReviewSeverity
from app.models.task import TaskEvent
from app.models.worker import AgentRun
from app.schemas.gemini import (
    GeminiAgentRunFact,
    GeminiCommandRunFact,
    GeminiEventFact,
    GeminiGateFact,
    GeminiReviewSummary,
    GeminiSafeNextAction,
    GeminiTaskFact,
    GeminiTaskFacts,
)
from app.services.task_service import get_task_or_404


MAX_EXCERPT_LENGTH = 700

GATE_FACTS: dict[TaskStatus, GeminiGateFact] = {
    TaskStatus.PLAN_READY: GeminiGateFact(
        type="PLAN_APPROVAL",
        owner="Human Supervisor",
        reason="Codex has prepared a plan. The Human Supervisor must confirm it before implementation.",
    ),
    TaskStatus.ACCEPTANCE_READY: GeminiGateFact(
        type="ACCEPTANCE_APPROVAL",
        owner="Human Supervisor",
        reason="The task is ready for acceptance. The Human Supervisor must make the final acceptance decision.",
    ),
}

NEXT_ACTION_LABELS: dict[TaskStatus, tuple[str, str]] = {
    TaskStatus.PLAN_REQUESTED: ("REQUEST_CODEX_PLAN", "Ask Codex to prepare the implementation plan."),
    TaskStatus.PLAN_CONFIRMED: ("START_CODEX_IMPLEMENTATION", "Ask Codex to implement the confirmed plan."),
    TaskStatus.IMPLEMENT_DONE: ("REQUEST_REVIEW", "Ask Claude-DeepSeek to review the implementation."),
    TaskStatus.FIX_REQUIRED: ("START_CODEX_FIX", "Ask Codex to fix open review items."),
    TaskStatus.FIX_DONE: ("REQUEST_RECHECK", "Ask Claude-DeepSeek to recheck the fixes."),
    TaskStatus.ACCEPTANCE_PASSED: ("START_ARCHIVE", "Ask Codex to update README archive documentation."),
    TaskStatus.ARCHIVED: ("MARK_DONE", "Mark the task as done after archive completion."),
}


def build_gemini_task_facts(session: Session, task_id: int) -> GeminiTaskFacts:
    task = get_task_or_404(session, task_id)
    allowed_next_statuses = sorted(ALLOWED_TRANSITIONS.get(task.status, set()), key=lambda status: status.value)

    events = session.exec(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.desc()).limit(8)
    ).all()
    agent_runs = session.exec(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.created_at.desc()).limit(5)
    ).all()
    review_items = session.exec(select(ReviewItem).where(ReviewItem.task_id == task_id)).all()
    command_runs = session.exec(
        select(CommandRun).where(CommandRun.task_id == task_id).order_by(CommandRun.created_at.desc()).limit(5)
    ).all()

    # Gemini receives a read-only fact package instead of direct database or
    # workspace access. This keeps Secretary answers grounded without giving it
    # authority to mutate task state or external project files.
    payload = {
        "task": GeminiTaskFact(
            id=task.id,
            title=task.title,
            description=task.description,
            workspace_path=task.workspace_path,
            status=task.status,
            priority=task.priority,
        ),
        "current_gate": get_current_gate(task.status),
        "allowed_next_statuses": allowed_next_statuses,
        "recent_events": [
            GeminiEventFact(
                event_type=event.event_type,
                from_status=event.from_status,
                to_status=event.to_status,
                message=event.message,
                created_by=event.created_by,
                created_at=event.created_at.isoformat(),
            )
            for event in events
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
            for run in agent_runs
        ],
        "review_summary": build_review_summary(review_items),
        "recent_commands": [
            GeminiCommandRunFact(
                id=command.id,
                command_key=command.command_key,
                status=command.status,
                exit_code=command.exit_code,
                duration_ms=command.duration_ms,
                created_at=command.created_at.isoformat(),
            )
            for command in command_runs
        ],
        "safe_next_actions": build_safe_next_actions(task.status, allowed_next_statuses),
    }

    return GeminiTaskFacts(
        facts_version=build_facts_version(payload),
        **payload,
    )


def build_facts_version(payload: dict) -> str:
    # The frontend uses this stable hash to decide whether a cached Gemini brief
    # is still valid after task events, runs, reviews, or command results change.
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


def build_safe_next_actions(
    status: TaskStatus,
    allowed_next_statuses: list[TaskStatus],
) -> list[GeminiSafeNextAction]:
    actions: list[GeminiSafeNextAction] = []
    if status in GATE_FACTS:
        gate = GATE_FACTS[status]
        actions.append(
            GeminiSafeNextAction(
                type=gate.type,
                label=f"Wait for {gate.owner}",
                requires_human=True,
                reason=gate.reason,
            )
        )
        return actions

    if len(allowed_next_statuses) != 1:
        return actions

    next_status = allowed_next_statuses[0]
    action_type, reason = NEXT_ACTION_LABELS.get(
        status,
        (f"ADVANCE_TO_{next_status.value}", f"Current status can advance to {next_status.value}."),
    )
    actions.append(
        GeminiSafeNextAction(
            type=action_type,
            label=next_status.value,
            requires_human=False,
            reason=reason,
        )
    )
    return actions


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
