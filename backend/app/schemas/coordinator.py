from typing import Literal

from pydantic import BaseModel, Field

from app.core.state_machine import TaskStatus
from app.models.worker import RunStatus
from app.schemas.workflow import ResolvedWorkflowAction


CoordinatorDecisionValue = Literal["continue", "stop"]
CoordinatorConfidence = Literal["high", "medium", "low"]


class CoordinatorDecision(BaseModel):
    decision: CoordinatorDecisionValue
    selected_action_id: str | None = None
    confidence: CoordinatorConfidence
    reason: str = Field(min_length=1)
    risk_notes: list[str] = Field(default_factory=list)


class CoordinatorDecisionResult(BaseModel):
    ok: bool = True
    model: str
    facts_version: str
    decision: CoordinatorDecision
    validation_errors: list[str] = Field(default_factory=list)


class CoordinatorActionValidation(BaseModel):
    allowed: bool
    action: ResolvedWorkflowAction | None = None
    errors: list[str] = Field(default_factory=list)


class CoordinatorStepResult(BaseModel):
    ok: bool = True
    executed: bool = False
    decision: CoordinatorDecision
    action_id: str | None = None
    action_label: str | None = None
    task_status_before: TaskStatus
    task_status_after: TaskStatus
    agent_run_id: int | None = None
    agent_run_status: RunStatus | None = None
    stop_reason: str | None = None
    validation_errors: list[str] = Field(default_factory=list)


class CoordinatorRunResult(BaseModel):
    ok: bool = True
    executed_steps: int = 0
    stopped: bool = True
    stop_reason: str | None = None
    steps: list[CoordinatorStepResult] = Field(default_factory=list)
