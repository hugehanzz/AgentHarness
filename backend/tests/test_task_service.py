import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.core.state_machine import TaskStatus
from app.models.task import TaskEvent
from app.models.worker import AgentRun, RunStatus
from app.schemas.task import TaskCreate
from app.services.task_service import create_task, transition_task, update_task_requirement


def test_create_and_transition_task():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Test", description="Requirement"))
        assert task.status == TaskStatus.REQUIREMENT_DRAFT

        updated = transition_task(session, task.id, TaskStatus.PLAN_REQUESTED, "request plan", "tester")
        assert updated.status == TaskStatus.PLAN_REQUESTED


def test_update_task_requirement_records_event():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Test", description="Requirement"))

        updated = update_task_requirement(session, task.id, "Updated requirement", "tester")

        assert updated.description == "Updated requirement"
        event = session.exec(
            select(TaskEvent).where(TaskEvent.task_id == task.id, TaskEvent.event_type == "REQUIREMENT_UPDATED")
        ).one()
        assert event.created_by == "tester"


def test_update_task_requirement_rejects_empty_description():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Test", description="Requirement"))

        with pytest.raises(HTTPException) as exc_info:
            update_task_requirement(session, task.id, "   ", "tester")

        assert exc_info.value.status_code == 400


def test_acceptance_pass_requires_successful_codex_checklist():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Accept task", description="Requirement"))
        task.status = TaskStatus.ACCEPTANCE_READY
        session.add(task)
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            transition_task(session, task.id, TaskStatus.ACCEPTANCE_PASSED, "accept", "tester")

        assert exc_info.value.status_code == 400
        assert "acceptance checklist" in exc_info.value.detail


def test_review_done_to_acceptance_requires_successful_claude_recheck():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Review task", description="Requirement"))
        task.status = TaskStatus.REVIEW_DONE
        session.add(task)
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            transition_task(session, task.id, TaskStatus.ACCEPTANCE_READY, "acceptance", "tester")

        assert exc_info.value.status_code == 400
        assert "Claude recheck" in exc_info.value.detail


def test_review_done_to_acceptance_allows_successful_claude_recheck():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Review task", description="Requirement"))
        task.status = TaskStatus.REVIEW_DONE
        session.add(task)
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="claude_recheck",
                provider_type="claude_cli",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()

        updated = transition_task(session, task.id, TaskStatus.ACCEPTANCE_READY, "acceptance", "tester")

        assert updated.status == TaskStatus.ACCEPTANCE_READY


def test_acceptance_pass_allows_successful_codex_checklist():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Accept task", description="Requirement"))
        task.status = TaskStatus.ACCEPTANCE_READY
        session.add(task)
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="codex_acceptance_checklist",
                provider_type="codex_app_server",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()

        updated = transition_task(session, task.id, TaskStatus.ACCEPTANCE_PASSED, "accept", "tester")

        assert updated.status == TaskStatus.ACCEPTANCE_PASSED
