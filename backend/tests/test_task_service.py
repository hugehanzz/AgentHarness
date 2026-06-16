import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.core.state_machine import TaskStatus
from app.models.task import TaskEvent
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
