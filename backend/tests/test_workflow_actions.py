from app.core.state_machine import ALLOWED_TRANSITIONS, TaskStatus
from app.core.workflow_actions import (
    AgentRunTiming,
    WORKFLOW_ACTIONS,
    get_workflow_action,
    get_workflow_actions,
)


def test_workflow_action_catalog_covers_every_state_machine_transition_once():
    catalog_transitions = [
        (action.from_status, action.to_status)
        for action in WORKFLOW_ACTIONS
    ]
    expected_transitions = {
        (from_status, to_status)
        for from_status, next_statuses in ALLOWED_TRANSITIONS.items()
        for to_status in next_statuses
    }

    assert len(catalog_transitions) == len(set(catalog_transitions))
    assert set(catalog_transitions) == expected_transitions


def test_workflow_action_ids_are_unique():
    action_ids = [action.action_id for action in WORKFLOW_ACTIONS]

    assert len(action_ids) == len(set(action_ids))


def test_workflow_actions_use_product_button_labels():
    assert get_workflow_action(
        TaskStatus.IMPLEMENTING,
        TaskStatus.IMPLEMENT_DONE,
    ).label == "标记开发完成"
    assert get_workflow_action(
        TaskStatus.FIX_DONE,
        TaskStatus.RECHECK_REQUESTED,
    ).label == "请求复审"
    assert get_workflow_action(
        TaskStatus.ARCHIVED,
        TaskStatus.DONE,
    ).label == "标记完成"


def test_review_to_acceptance_enters_finalize_without_running_agent():
    action = get_workflow_action(
        TaskStatus.REVIEW_DONE,
        TaskStatus.FINALIZE_REQUESTED,
    )

    assert action.agent_run_type is None
    assert action.agent_run_timing is None


def test_finalize_completion_requires_separate_transition():
    action = get_workflow_action(
        TaskStatus.FINALIZE_REQUESTED,
        TaskStatus.ACCEPTANCE_READY,
    )

    assert action.label == "标记封板完成"


def test_human_gate_actions_are_explicit():
    assert get_workflow_action(
        TaskStatus.PLAN_READY,
        TaskStatus.PLAN_CONFIRMED,
    ).requires_human_gate
    assert get_workflow_action(
        TaskStatus.ACCEPTANCE_READY,
        TaskStatus.ACCEPTANCE_PASSED,
    ).requires_human_gate


def test_get_workflow_actions_returns_current_state_actions_only():
    actions = get_workflow_actions(TaskStatus.RECHECK_DONE)

    assert {action.label for action in actions} == {"进入验收", "要求修复"}


def test_finalize_state_exposes_mark_complete_action():
    actions = get_workflow_actions(TaskStatus.FINALIZE_REQUESTED)

    assert {action.label for action in actions} == {"标记封板完成"}
