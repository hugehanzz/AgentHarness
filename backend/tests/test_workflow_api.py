from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import app.models  # noqa: F401
from app.api import tasks
from app.core.database import get_session
from app.core.state_machine import TaskStatus
from app.schemas.task import TaskCreate
from app.services.task_service import create_task


def test_task_workflow_endpoint_returns_resolved_actions():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Build", description="Requirement"))
        task.status = TaskStatus.IMPLEMENTING
        session.add(task)
        session.commit()
        task_id = task.id

    app = FastAPI()
    app.include_router(tasks.router)

    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    response = TestClient(app).get(f"/tasks/{task_id}/workflow")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_status"] == "IMPLEMENTING"
    assert payload["activity"]["agent_run_type"] == "codex_implement"
    assert payload["actions"][0]["label"] == "标记开发完成"
    assert payload["actions"][0]["enabled"] is False
    assert "Codex 开发" in payload["actions"][0]["blocked_reason"]
