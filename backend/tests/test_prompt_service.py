from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.prompt import PromptRecord, PromptType
from app.schemas.task import TaskCreate
from app.services.prompt_service import create_prompt, preview_prompt
from app.services.task_service import create_task


def test_preview_prompt_does_not_create_prompt_record():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Preview task", description="Requirement"))

        content = preview_prompt(session, task.id, PromptType.CODEX_PLAN)

        assert "任务标题：Preview task" in content
        assert session.exec(select(PromptRecord)).all() == []


def test_create_prompt_still_records_prompt():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Record task", description="Requirement"))

        record = create_prompt(session, task.id, PromptType.CODEX_PLAN)

        assert record.content
        assert session.exec(select(PromptRecord)).one().id == record.id
