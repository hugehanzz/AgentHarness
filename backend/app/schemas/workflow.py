from enum import StrEnum

from pydantic import BaseModel, Field

from app.core.state_machine import TaskStatus
from app.core.workflow_actions import AgentRunTiming
from app.models.worker import RunStatus


class WorkflowActivityState(StrEnum):
    WAITING_FOR_USER = "WAITING_FOR_USER"
    WAITING_FOR_HUMAN_GATE = "WAITING_FOR_HUMAN_GATE"
    AGENT_RUNNING = "AGENT_RUNNING"
    AGENT_SUCCEEDED = "AGENT_SUCCEEDED"
    AGENT_FAILED = "AGENT_FAILED"
    COMPLETED = "COMPLETED"


class WorkflowActivity(BaseModel):
    state: WorkflowActivityState
    message: str
    agent_run_type: str | None = None
    run_status: RunStatus | None = None
    run_id: int | None = None


class WorkflowActionEvidence(BaseModel):
    required_run_type: str
    latest_run_status: RunStatus | None = None
    latest_run_id: int | None = None
    satisfied: bool = False


class ResolvedWorkflowAction(BaseModel):
    action_id: str
    label: str
    from_status: TaskStatus
    to_status: TaskStatus
    enabled: bool
    recommended: bool
    requires_human_gate: bool = False
    agent_run_type: str | None = None
    agent_run_timing: AgentRunTiming | None = None
    instruction: str
    side_effects: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    evidence: WorkflowActionEvidence | None = None


class ResolvedWorkflowState(BaseModel):
    task_id: int
    current_status: TaskStatus
    activity: WorkflowActivity
    actions: list[ResolvedWorkflowAction]
