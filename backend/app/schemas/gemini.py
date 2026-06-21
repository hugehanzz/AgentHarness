from pydantic import BaseModel, Field
from typing import Literal

from app.core.state_machine import TaskStatus
from app.models.command import CommandStatus
from app.models.task import TaskPriority
from app.models.worker import RunStatus


class GeminiTestRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)


class GeminiTextResponse(BaseModel):
    ok: bool
    model: str
    text: str
    finish_reason: str | None = None


class GeminiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class GeminiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[GeminiChatMessage] = Field(default_factory=list, max_length=8)


class GeminiTaskFact(BaseModel):
    id: int
    title: str
    description: str
    workspace_path: str | None
    status: TaskStatus
    priority: TaskPriority


class GeminiGateFact(BaseModel):
    type: str
    owner: str
    reason: str
    blocks_auto_advance: bool = True


class GeminiEventFact(BaseModel):
    event_type: str
    from_status: TaskStatus | None
    to_status: TaskStatus | None
    message: str | None
    created_by: str
    created_at: str


class GeminiAgentRunFact(BaseModel):
    id: int
    run_type: str
    provider_type: str
    status: RunStatus
    output_excerpt: str | None
    error_message: str | None
    finished_at: str | None
    created_at: str


class GeminiReviewSummary(BaseModel):
    total_count: int
    open_count: int
    high_open_count: int
    medium_open_count: int
    low_open_count: int
    unknown_open_count: int
    open_items: list[str]


class GeminiCommandRunFact(BaseModel):
    id: int
    command_key: str
    status: CommandStatus
    exit_code: int | None
    duration_ms: int | None
    created_at: str


class GeminiSafeNextAction(BaseModel):
    type: str
    label: str
    requires_human: bool
    reason: str


class GeminiTaskFacts(BaseModel):
    facts_version: str
    task: GeminiTaskFact
    current_gate: GeminiGateFact | None
    allowed_next_statuses: list[TaskStatus]
    recent_events: list[GeminiEventFact]
    latest_agent_runs: list[GeminiAgentRunFact]
    review_summary: GeminiReviewSummary
    recent_commands: list[GeminiCommandRunFact]
    safe_next_actions: list[GeminiSafeNextAction]


class GeminiTaskBrief(BaseModel):
    ok: bool = True
    model: str
    facts_version: str
    summary: str
    current_position: str
    pending_gate: GeminiGateFact | None
    suggested_next_steps: list[str]
    risk_notes: list[str]
