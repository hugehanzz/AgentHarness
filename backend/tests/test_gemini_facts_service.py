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
        assert facts.current_gate.type == "计划确认"
        assert facts.current_gate.owner == "Human Supervisor"
        assert facts.workflow_guidance.activity.state == "WAITING_FOR_HUMAN_GATE"
        assert facts.workflow_guidance.available_user_actions[0].label == "确认计划"
        assert facts.workflow_guidance.available_user_actions[0].requires_human_gate is True
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
        assert facts.workflow_guidance.available_user_actions[0].label == "请求评审"
        assert facts.workflow_guidance.available_user_actions[0].enabled is True
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


def test_gemini_workflow_guidance_recommends_acceptance_when_review_has_no_open_items():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Review done", description="Requirement"))
        task.status = TaskStatus.REVIEW_DONE
        session.add(task)
        session.commit()

        facts = build_gemini_task_facts(session, task.id)

        actions = {action.label: action for action in facts.workflow_guidance.available_user_actions}
        assert facts.workflow_guidance.current_status_label == "评审完成"
        assert "进入验收" in actions
        assert "要求修复" in actions
        assert actions["进入验收"].recommended is True
        assert actions["进入验收"].side_effects == ["任务进入“等待审查封板”状态"]


def test_gemini_workflow_guidance_recommends_fix_when_review_has_open_items():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Review done", description="Requirement"))
        task.status = TaskStatus.REVIEW_DONE
        session.add(task)
        session.add(
            ReviewItem(
                task_id=task.id,
                severity=ReviewSeverity.HIGH,
                title="Missing validation",
                status=ReviewItemStatus.OPEN,
            )
        )
        session.commit()

        facts = build_gemini_task_facts(session, task.id)

        actions = {action.label: action for action in facts.workflow_guidance.available_user_actions}
        assert actions["要求修复"].recommended is True
        assert actions["进入验收"].recommended is False


def test_gemini_review_summary_treats_fixed_pending_recheck_as_open():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Recheck pending", description="Requirement"))
        task.status = TaskStatus.RECHECK_DONE
        session.add(task)
        session.add(
            ReviewItem(
                task_id=task.id,
                severity=ReviewSeverity.MEDIUM,
                title="Claimed fixed but not rechecked",
                status=ReviewItemStatus.FIXED_PENDING_RECHECK,
            )
        )
        session.commit()

        facts = build_gemini_task_facts(session, task.id)
        actions = {action.label: action for action in facts.workflow_guidance.available_user_actions}

        assert facts.review_summary.open_count == 1
        assert facts.review_summary.medium_open_count == 1
        assert facts.review_summary.open_items == ["Claimed fixed but not rechecked"]
        assert actions["要求修复"].recommended is True
        assert actions["进入验收"].recommended is False


def test_gemini_facts_use_current_product_button_after_agent_succeeds():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Implementing", description="Requirement"))
        task.status = TaskStatus.IMPLEMENTING
        session.add(task)
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="codex_implement",
                provider_type="codex_app_server",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()

        facts = build_gemini_task_facts(session, task.id)
        action = facts.workflow_guidance.available_user_actions[0]

        assert facts.workflow_guidance.activity.state == "AGENT_SUCCEEDED"
        assert action.label == "标记开发完成"
        assert action.enabled is True
        assert action.agent_run_type is None


def test_gemini_action_side_effects_do_not_expose_internal_status_names():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        task = create_task(session, TaskCreate(title="Review", description="Requirement"))
        task.status = TaskStatus.IMPLEMENT_DONE
        session.add(task)
        session.commit()

        facts = build_gemini_task_facts(session, task.id)
        action = facts.workflow_guidance.available_user_actions[0]

        assert action.label == "请求评审"
        assert all("REVIEW_REQUESTED" not in effect for effect in action.side_effects)
        assert any("评审中" in effect for effect in action.side_effects)
