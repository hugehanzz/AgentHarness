from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.models.prompt import PromptType
from app.prompts.templates import build_prompt
from app.schemas.task import TaskCreate
from app.services.prompt_service import preview_prompt
from app.services.task_service import create_task


def test_preview_prompt_does_not_create_prompt_table_or_record():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Preview task", description="Requirement"))

        content = preview_prompt(session, task.id, PromptType.CODEX_PLAN)

        assert "任务标题：Preview task" in content
        assert f"任务 ID：{task.id}" not in content
        assert not inspect(engine).has_table("promptrecord")


def test_prompt_project_name_uses_workspace_leaf_directory():
    task = type(
        "TaskStub",
        (),
        {
            "id": 26,
            "title": "Automation",
            "status": "DONE",
            "workspace_path": r"D:\codexProject\AgentHarnessTest",
            "description": "Requirement",
        },
    )()

    content = build_prompt(task, PromptType.CODEX_PLAN)

    assert "项目：AgentHarnessTest" in content
    assert r"工作区路径：D:\codexProject\AgentHarnessTest" in content


def test_prompt_project_name_falls_back_without_workspace_path():
    task = type(
        "TaskStub",
        (),
        {
            "id": 1,
            "title": "No workspace",
            "status": "REQUIREMENT_DRAFT",
            "workspace_path": None,
            "description": "Requirement",
        },
    )()

    content = build_prompt(task, PromptType.CODEX_PLAN)

    assert "项目：AgentHarness 托管工作区" in content


def test_claude_recheck_and_finalize_prompts_keep_separate_responsibilities():
    task = type(
        "TaskStub",
        (),
        {
            "id": 1,
            "title": "Review",
            "status": "RECHECK_DONE",
            "workspace_path": "D:/workspace",
            "description": "Requirement",
        },
    )()

    recheck = build_prompt(task, PromptType.CLAUDE_RECHECK)
    finalize = build_prompt(task, PromptType.CLAUDE_FINALIZE)

    assert "不要执行封板" in recheck
    assert "最终审查封板" in finalize
    assert "不要重新进行全面代码评审" in finalize
