from enum import StrEnum


class TaskStatus(StrEnum):
    REQUIREMENT_DRAFT = "REQUIREMENT_DRAFT"
    PLAN_REQUESTED = "PLAN_REQUESTED"
    PLAN_READY = "PLAN_READY"
    PLAN_CONFIRMED = "PLAN_CONFIRMED"
    IMPLEMENTING = "IMPLEMENTING"
    IMPLEMENT_DONE = "IMPLEMENT_DONE"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    REVIEW_DONE = "REVIEW_DONE"
    FIX_REQUIRED = "FIX_REQUIRED"
    FIXING = "FIXING"
    FIX_DONE = "FIX_DONE"
    RECHECK_REQUESTED = "RECHECK_REQUESTED"
    RECHECK_DONE = "RECHECK_DONE"
    FINALIZE_REQUESTED = "FINALIZE_REQUESTED"
    ACCEPTANCE_READY = "ACCEPTANCE_READY"
    ACCEPTANCE_PASSED = "ACCEPTANCE_PASSED"
    ARCHIVED = "ARCHIVED"
    DONE = "DONE"


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.REQUIREMENT_DRAFT: {TaskStatus.PLAN_REQUESTED},
    TaskStatus.PLAN_REQUESTED: {TaskStatus.PLAN_READY},
    TaskStatus.PLAN_READY: {TaskStatus.PLAN_CONFIRMED},
    TaskStatus.PLAN_CONFIRMED: {TaskStatus.IMPLEMENTING},
    TaskStatus.IMPLEMENTING: {TaskStatus.IMPLEMENT_DONE},
    TaskStatus.IMPLEMENT_DONE: {TaskStatus.REVIEW_REQUESTED},
    TaskStatus.REVIEW_REQUESTED: {TaskStatus.REVIEW_DONE},
    TaskStatus.REVIEW_DONE: {TaskStatus.FIX_REQUIRED, TaskStatus.FINALIZE_REQUESTED},
    TaskStatus.FIX_REQUIRED: {TaskStatus.FIXING},
    TaskStatus.FIXING: {TaskStatus.FIX_DONE},
    TaskStatus.FIX_DONE: {TaskStatus.RECHECK_REQUESTED},
    TaskStatus.RECHECK_REQUESTED: {TaskStatus.RECHECK_DONE},
    TaskStatus.RECHECK_DONE: {TaskStatus.FIX_REQUIRED, TaskStatus.FINALIZE_REQUESTED},
    TaskStatus.FINALIZE_REQUESTED: {TaskStatus.ACCEPTANCE_READY},
    TaskStatus.ACCEPTANCE_READY: {TaskStatus.ACCEPTANCE_PASSED},
    TaskStatus.ACCEPTANCE_PASSED: {TaskStatus.ARCHIVED},
    TaskStatus.ARCHIVED: {TaskStatus.DONE},
    TaskStatus.DONE: set(),
}


# 这些状态故意停止自动化。后端可以描述门禁，但只有 Human Supervisor 才能做出离开该状态的决策。
HUMAN_GATE_STATUSES = {
    TaskStatus.PLAN_READY,
    TaskStatus.ACCEPTANCE_READY,
}


def can_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())
