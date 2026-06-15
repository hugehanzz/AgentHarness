from app.core.state_machine import TaskStatus, can_transition


def test_allows_expected_transition():
    assert can_transition(TaskStatus.REQUIREMENT_DRAFT, TaskStatus.PLAN_REQUESTED)


def test_rejects_unexpected_transition():
    assert not can_transition(TaskStatus.REQUIREMENT_DRAFT, TaskStatus.DONE)
