from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, select

from app.models.command import CommandRun
from app.models.review import ReviewItem
from app.models.task import Task, TaskEvent
from app.models.worker import AgentRun
from app.services.task_service import get_task_or_404


@dataclass(frozen=True)
class WorkflowContextSnapshot:
    task: Task
    evidence_started_at: datetime | None
    current_status_agent_runs: list[AgentRun]
    review_items: list[ReviewItem]


@dataclass(frozen=True)
class TaskContextSnapshot(WorkflowContextSnapshot):
    recent_events: list[TaskEvent]
    recent_agent_runs: list[AgentRun]
    recent_commands: list[CommandRun]


def load_workflow_context_snapshot(
    session: Session,
    task_id: int,
) -> WorkflowContextSnapshot:
    task = get_task_or_404(session, task_id)
    evidence_started_at = get_workflow_evidence_started_at(session, task)
    return WorkflowContextSnapshot(
        task=task,
        evidence_started_at=evidence_started_at,
        current_status_agent_runs=get_current_status_agent_runs(
            session,
            task,
            evidence_started_at,
        ),
        review_items=list(
            session.exec(select(ReviewItem).where(ReviewItem.task_id == task.id)).all()
        ),
    )


def load_task_context_snapshot(
    session: Session,
    task_id: int,
) -> TaskContextSnapshot:
    workflow = load_workflow_context_snapshot(session, task_id)
    return TaskContextSnapshot(
        task=workflow.task,
        evidence_started_at=workflow.evidence_started_at,
        current_status_agent_runs=workflow.current_status_agent_runs,
        review_items=workflow.review_items,
        recent_events=list(
            session.exec(
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id)
                .order_by(TaskEvent.created_at.desc())
                .limit(8)
            ).all()
        ),
        recent_agent_runs=list(
            session.exec(
                select(AgentRun)
                .where(AgentRun.task_id == task_id)
                .order_by(AgentRun.created_at.desc())
                .limit(5)
            ).all()
        ),
        recent_commands=list(
            session.exec(
                select(CommandRun)
                .where(CommandRun.task_id == task_id)
                .order_by(CommandRun.created_at.desc())
                .limit(5)
            ).all()
        ),
    )


def get_workflow_evidence_started_at(
    session: Session,
    task: Task,
) -> datetime | None:
    status_event = session.exec(
        select(TaskEvent)
        .where(
            TaskEvent.task_id == task.id,
            TaskEvent.to_status == task.status,
        )
        .order_by(TaskEvent.created_at.desc())
    ).first()
    requirement_event = session.exec(
        select(TaskEvent)
        .where(
            TaskEvent.task_id == task.id,
            TaskEvent.event_type == "REQUIREMENT_UPDATED",
        )
        .order_by(TaskEvent.created_at.desc())
    ).first()
    timestamps = [
        event.created_at
        for event in (status_event, requirement_event)
        if event is not None
    ]
    return max(timestamps) if timestamps else None


def get_current_status_agent_runs(
    session: Session,
    task: Task,
    entered_at: datetime | None,
) -> list[AgentRun]:
    statement = select(AgentRun).where(AgentRun.task_id == task.id)
    if entered_at is not None:
        statement = statement.where(AgentRun.created_at >= entered_at)
    return list(session.exec(statement.order_by(AgentRun.created_at.desc())).all())
