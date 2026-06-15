from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.state_machine import TaskStatus
from app.schemas.task import TaskCreate
from app.services.task_service import create_task, transition_task


def test_create_and_transition_task():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Test", description="Requirement"))
        assert task.status == TaskStatus.REQUIREMENT_DRAFT

        updated = transition_task(session, task.id, TaskStatus.PLAN_REQUESTED, "request plan", "tester")
        assert updated.status == TaskStatus.PLAN_REQUESTED
