from typing import Literal

from pydantic import BaseModel, Field


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

