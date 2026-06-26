from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.core.state_machine import TaskStatus
from app.models.review import ReviewItem, ReviewItemStatus, ReviewSeverity
from app.models.worker import AgentRun, RunStatus
from app.schemas.task import TaskCreate
from app.schemas.workflow import WorkflowActivityState
from app.services.task_service import create_task, transition_task
from app.services.workflow_action_service import resolve_task_workflow


def create_memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_resolver_blocks_completion_until_current_agent_run_succeeds():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Build", description="Requirement"))
        task.status = TaskStatus.IMPLEMENTING
        session.add(task)
        session.commit()

        state = resolve_task_workflow(session, task.id)

        assert state.activity.state == WorkflowActivityState.WAITING_FOR_USER
        assert state.activity.agent_run_type == "codex_implement"
        assert len(state.actions) == 1
        assert state.actions[0].label == "标记开发完成"
        assert state.actions[0].enabled is False
        assert "Codex 开发" in state.actions[0].blocked_reason


def test_resolver_enables_completion_after_successful_current_agent_run():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Build", description="Requirement"))
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

        state = resolve_task_workflow(session, task.id)

        assert state.activity.state == WorkflowActivityState.AGENT_SUCCEEDED
        assert state.actions[0].enabled is True
        assert state.actions[0].recommended is True
        assert state.actions[0].evidence.satisfied is True


def test_resolver_reports_running_agent_and_disables_completion():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Review", description="Requirement"))
        task.status = TaskStatus.REVIEW_REQUESTED
        session.add(task)
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="claude_review",
                provider_type="claude_cli",
                status=RunStatus.RUNNING,
            )
        )
        session.commit()

        state = resolve_task_workflow(session, task.id)

        assert state.activity.state == WorkflowActivityState.AGENT_RUNNING
        assert state.actions[0].label == "标记评审完成"
        assert state.actions[0].enabled is False
        assert "正在运行" in state.actions[0].blocked_reason


def test_resolver_recommends_fix_when_review_has_open_items():
    with create_memory_session() as session:
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

        state = resolve_task_workflow(session, task.id)
        actions = {action.label: action for action in state.actions}

        assert actions["要求修复"].recommended is True
        assert actions["进入验收"].recommended is False
        assert actions["进入验收"].agent_run_type is None
        assert actions["进入验收"].agent_run_timing is None


def test_resolver_recommends_fix_when_review_has_fixed_pending_recheck_items():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Review done", description="Requirement"))
        task.status = TaskStatus.REVIEW_DONE
        session.add(task)
        session.add(
            ReviewItem(
                task_id=task.id,
                severity=ReviewSeverity.HIGH,
                title="Needs recheck",
                status=ReviewItemStatus.FIXED_PENDING_RECHECK,
            )
        )
        session.commit()

        state = resolve_task_workflow(session, task.id)
        actions = {action.label: action for action in state.actions}

        assert actions["要求修复"].recommended is True
        assert actions["进入验收"].recommended is False


def test_resolver_recommends_acceptance_when_review_has_no_open_items():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Review done", description="Requirement"))
        task.status = TaskStatus.REVIEW_DONE
        session.add(task)
        session.commit()

        state = resolve_task_workflow(session, task.id)
        actions = {action.label: action for action in state.actions}

        assert actions["进入验收"].recommended is True
        assert actions["要求修复"].recommended is False
        assert actions["进入验收"].side_effects == ["任务进入“等待审查封板”状态"]


def test_resolver_requires_successful_finalize_before_acceptance_ready():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Finalize", description="Requirement"))
        task.status = TaskStatus.FINALIZE_REQUESTED
        session.add(task)
        session.commit()

        state = resolve_task_workflow(session, task.id)

        assert state.activity.agent_run_type == "claude_finalize"
        assert state.actions[0].label == "标记封板完成"
        assert state.actions[0].enabled is False

        session.add(
            AgentRun(
                task_id=task.id,
                run_type="claude_finalize",
                provider_type="claude_cli",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()

        state = resolve_task_workflow(session, task.id)
        assert state.actions[0].enabled is True


def test_resolver_blocks_acceptance_without_successful_checklist():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Accept", description="Requirement"))
        task.status = TaskStatus.ACCEPTANCE_READY
        session.add(task)
        session.commit()

        state = resolve_task_workflow(session, task.id)

        assert state.activity.state == WorkflowActivityState.WAITING_FOR_HUMAN_GATE
        assert state.activity.agent_run_type == "codex_acceptance_checklist"
        assert state.actions[0].label == "标记验收通过"
        assert state.actions[0].enabled is False
        assert state.actions[0].requires_human_gate is True
        assert state.actions[0].recommended is False


def test_resolver_keeps_acceptance_as_human_gate_after_checklist_succeeds():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Accept", description="Requirement"))
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

        state = resolve_task_workflow(session, task.id)

        assert state.activity.state == WorkflowActivityState.WAITING_FOR_HUMAN_GATE
        assert "等待 Human Supervisor" in state.activity.message
        assert state.actions[0].enabled is True
        assert state.actions[0].recommended is False


def test_resolver_ignores_agent_runs_created_before_current_status():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Repeated fix", description="Requirement"))
        session.add(
            AgentRun(
                task_id=task.id,
                run_type="codex_fix",
                provider_type="codex_app_server",
                status=RunStatus.SUCCEEDED,
            )
        )
        session.commit()
        transition_task(session, task.id, TaskStatus.PLAN_REQUESTED, "plan", "tester")
        task.status = TaskStatus.FIXING
        session.add(task)
        session.commit()
        transition_event = task.updated_at

        # 在陈旧的成功 run 之后记录进入当前状态。
        from app.models.task import TaskEvent

        session.add(
            TaskEvent(
                task_id=task.id,
                event_type="TASK_TRANSITIONED",
                from_status=TaskStatus.FIX_REQUIRED,
                to_status=TaskStatus.FIXING,
                message="start another fix round",
                created_by="tester",
                created_at=transition_event,
            )
        )
        session.commit()

        state = resolve_task_workflow(session, task.id)

        assert state.actions[0].label == "标记修复完成"
        assert state.actions[0].enabled is False
        assert state.actions[0].evidence.latest_run_id is None


def test_resolver_invalidates_agent_evidence_after_requirement_changes():
    with create_memory_session() as session:
        task = create_task(session, TaskCreate(title="Changed requirement", description="Original"))
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

        from app.services.task_service import update_task_requirement

        update_task_requirement(session, task.id, "Changed after implementation", "tester")
        state = resolve_task_workflow(session, task.id)

        assert state.actions[0].label == "标记开发完成"
        assert state.actions[0].enabled is False
        assert state.actions[0].evidence.latest_run_id is None
        assert state.activity.agent_run_type == "codex_implement"
