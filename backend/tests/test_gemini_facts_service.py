from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.state_machine import TaskStatus
from app.models.command import CommandRun, CommandStatus
from app.models.review import ReviewItem, ReviewItemStatus, ReviewSeverity
from app.models.worker import AgentRun, RunStatus
from app.schemas.task import TaskCreate
from app.services.gemini_facts_service import build_gemini_task_facts
from app.services.task_service import create_task, transition_task


def test_build_gemini_task_facts_identifies_human_gate():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Plan", description="Requirement"))
        transition_task(session, task.id, TaskStatus.PLAN_REQUESTED, "request plan", "tester")
        transition_task(session, task.id, TaskStatus.PLAN_READY, "plan ready", "codex")

        facts = build_gemini_task_facts(session, task.id)

        assert facts.task.status == TaskStatus.PLAN_READY
        assert facts.current_gate is not None
        assert facts.current_gate.type == "PLAN_APPROVAL"
        assert facts.current_gate.owner == "Human Supervisor"
        assert facts.allowed_next_statuses == [TaskStatus.PLAN_CONFIRMED]
        assert facts.safe_next_actions[0].requires_human is True
        assert len(facts.facts_version) == 64


def test_build_gemini_task_facts_summarizes_runs_reviews_and_commands():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Build", description="Requirement"))
        task.status = TaskStatus.IMPLEMENT_DONE
        session.add(task)
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="codex_implement",
                provider_type="codex_app_server",
                status=RunStatus.SUCCEEDED,
                output_payload="Implementation complete",
            )
        )
        session.add(
            ReviewItem(
                task_id=task.id,
                severity=ReviewSeverity.HIGH,
                title="Missing test",
                status=ReviewItemStatus.OPEN,
            )
        )
        session.add(
            CommandRun(
                task_id=task.id,
                command_key="backend_tests",
                command_display="pytest",
                cwd="D:\\workspace",
                status=CommandStatus.SUCCEEDED,
                exit_code=0,
                duration_ms=1200,
            )
        )
        session.commit()

        facts = build_gemini_task_facts(session, task.id)

        assert facts.current_gate is None
        assert facts.allowed_next_statuses == [TaskStatus.REVIEW_REQUESTED]
        assert facts.safe_next_actions[0].type == "REQUEST_REVIEW"
        assert facts.safe_next_actions[0].requires_human is False
        assert facts.latest_agent_runs[0].output_excerpt == "Implementation complete"
        assert facts.review_summary.open_count == 1
        assert facts.review_summary.high_open_count == 1
        assert facts.review_summary.open_items == ["Missing test"]
        assert facts.recent_commands[0].command_key == "backend_tests"


def test_gemini_task_facts_version_changes_when_events_change():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Version", description="Requirement"))
        first = build_gemini_task_facts(session, task.id)

        transition_task(session, task.id, TaskStatus.PLAN_REQUESTED, "request plan", "tester")
        second = build_gemini_task_facts(session, task.id)

        assert first.facts_version != second.facts_version
