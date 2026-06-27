from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import app.models  # noqa: F401
from app.api import coordinator
from app.core.database import get_session
from app.schemas.task import TaskCreate
from app.services.task_service import create_task


def test_coordinator_step_endpoint_returns_stop_result_for_secretary_task():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Secretary", description="Requirement"))
        task_id = task.id

    app = FastAPI()
    app.include_router(coordinator.router)

    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    response = TestClient(app).post(f"/coordinator/tasks/{task_id}/step")

    assert response.status_code == 200
    payload = response.json()
    assert payload["executed"] is False
    assert payload["task_status_before"] == "REQUIREMENT_DRAFT"
    assert payload["task_status_after"] == "REQUIREMENT_DRAFT"
    assert "Coordinator" in payload["stop_reason"]


def test_coordinator_run_endpoint_returns_stop_result_for_secretary_task():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Secretary", description="Requirement"))
        task_id = task.id

    app = FastAPI()
    app.include_router(coordinator.router)

    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    response = TestClient(app).post(f"/coordinator/tasks/{task_id}/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["executed_steps"] == 0
    assert payload["stopped"] is True
    assert len(payload["steps"]) == 1
    assert "Coordinator" in payload["stop_reason"]
