from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.state_machine import TaskStatus, can_transition
from app.models.common import app_now
from app.models.task import Task, TaskEvent
from app.models.worker import AgentRun, RunStatus
from app.schemas.task import TaskCreate


def create_task(session: Session, payload: TaskCreate) -> Task:
    task = Task.model_validate(payload)
    session.add(task)
    session.commit()
    session.refresh(task)
    event = TaskEvent(
        task_id=task.id,
        event_type="TASK_CREATED",
        to_status=task.status,
        message="Task created",
        created_by="human_supervisor",
    )
    session.add(event)
    session.commit()
    return task


def list_tasks(session: Session) -> list[Task]:
    return list(session.exec(select(Task).order_by(Task.created_at.desc())).all())


def get_task_or_404(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def get_task_events(session: Session, task_id: int) -> list[TaskEvent]:
    return list(session.exec(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at)).all())


def has_successful_acceptance_checklist(session: Session, task_id: int) -> bool:
    # Acceptance is a human decision, but it must be preceded by Codex producing
    # an explicit checklist/evidence package for the supervisor to inspect.
    run = session.exec(
        select(AgentRun)
        .where(
            AgentRun.task_id == task_id,
            AgentRun.run_type == "codex_acceptance_checklist",
            AgentRun.status == RunStatus.SUCCEEDED,
        )
        .order_by(AgentRun.created_at.desc())
    ).first()
    return run is not None


def transition_task(session: Session, task_id: int, to_status: TaskStatus, message: str | None, created_by: str) -> Task:
    task = get_task_or_404(session, task_id)
    from_status = task.status
    if not can_transition(from_status, to_status):
        raise HTTPException(status_code=400, detail=f"Invalid transition: {from_status} -> {to_status}")
    # Guard the final acceptance gate with evidence, not just a button click.
    if (
        from_status == TaskStatus.ACCEPTANCE_READY
        and to_status == TaskStatus.ACCEPTANCE_PASSED
        and not has_successful_acceptance_checklist(session, task.id)
    ):
        raise HTTPException(status_code=400, detail="Codex acceptance checklist must succeed before acceptance can pass")
    task.status = to_status
    task.updated_at = app_now()
    if to_status == TaskStatus.ARCHIVED:
        task.archived_at = app_now()
    event = TaskEvent(
        task_id=task.id,
        event_type="TASK_TRANSITIONED",
        from_status=from_status,
        to_status=to_status,
        message=message,
        created_by=created_by,
    )
    session.add(task)
    session.add(event)
    session.commit()
    session.refresh(task)
    return task


def update_task_requirement(session: Session, task_id: int, description: str, created_by: str) -> Task:
    task = get_task_or_404(session, task_id)
    next_description = description.strip()
    if not next_description:
        raise HTTPException(status_code=400, detail="description must not be empty")
    if task.description == next_description:
        return task

    task.description = next_description
    task.updated_at = app_now()
    event = TaskEvent(
        task_id=task.id,
        event_type="REQUIREMENT_UPDATED",
        message="Requirement description updated",
        created_by=created_by,
    )
    session.add(task)
    session.add(event)
    session.commit()
    session.refresh(task)
    return task
