import json
import re

from fastapi import HTTPException

from app.models.task import TaskMode
from app.schemas.coordinator import CoordinatorDecision, CoordinatorDecisionResult
from app.schemas.gemini import GeminiTaskFacts
from app.schemas.workflow import ResolvedWorkflowAction, WorkflowActivityState
from app.services.gemini_service import generate_gemini_text


COORDINATOR_DECISION_JSON_SCHEMA = """{
  "decision": "continue or stop",
  "selected_action_id": "string action_id from candidate_actions, or null",
  "confidence": "high, medium, or low",
  "reason": "string, concise Chinese explanation",
  "risk_notes": ["string"]
}"""


def build_coordinator_decision_context(facts: GeminiTaskFacts) -> dict:
    candidates = safe_candidate_actions(facts)
    candidate_ids = {action.action_id for action in candidates}
    return {
        "task": {
            "title": facts.task.title,
            "description": facts.task.description,
            "mode": facts.task.mode.value,
            "status": facts.workflow_guidance.current_status_label,
            "stage": facts.workflow_guidance.current_stage_label,
        },
        "activity": {
            "state": facts.workflow_guidance.activity.state.value,
            "message": facts.workflow_guidance.activity.message,
            "agent_run_type": facts.workflow_guidance.activity.agent_run_type,
            "run_status": facts.workflow_guidance.activity.run_status.value
            if facts.workflow_guidance.activity.run_status
            else None,
        },
        "gate": facts.current_gate.model_dump(mode="json") if facts.current_gate else None,
        "candidate_actions": [
            coordinator_action_payload(action)
            for action in candidates
        ],
        "blocked_actions": [
            coordinator_action_payload(action)
            for action in facts.workflow_guidance.available_user_actions
            if action.action_id not in candidate_ids
        ],
        "latest_agent_runs": [
            {
                "run_type": run.run_type,
                "status": run.status.value,
                "output_excerpt": run.output_excerpt,
                "error_message": run.error_message,
            }
            for run in facts.latest_agent_runs[:5]
        ],
        "review_summary": facts.review_summary.model_dump(mode="json"),
        "recent_commands": [
            {
                "command_key": command.command_key,
                "status": command.status.value,
                "exit_code": command.exit_code,
                "duration_ms": command.duration_ms,
            }
            for command in facts.recent_commands[:5]
        ],
        "recent_events": [
            {
                "event_type": event.event_type,
                "message": event.message,
                "created_by": event.created_by,
                "created_at": event.created_at,
            }
            for event in facts.recent_events[:5]
        ],
    }


def coordinator_action_payload(action: ResolvedWorkflowAction) -> dict:
    return {
        "action_id": action.action_id,
        "label": action.label,
        "enabled": action.enabled,
        "recommended": action.recommended,
        "requires_human_gate": action.requires_human_gate,
        "instruction": action.instruction,
        "side_effects": action.side_effects,
        "blocked_reason": action.blocked_reason,
    }


def safe_candidate_actions(facts: GeminiTaskFacts) -> list[ResolvedWorkflowAction]:
    if facts.task.mode != TaskMode.COORDINATOR:
        return []
    if facts.current_gate is not None and facts.current_gate.blocks_auto_advance:
        return []
    if facts.workflow_guidance.activity.state == WorkflowActivityState.AGENT_RUNNING:
        return []
    return [
        action
        for action in facts.workflow_guidance.available_user_actions
        if action.enabled and not action.requires_human_gate
    ]


def build_coordinator_decision_prompt(facts: GeminiTaskFacts) -> str:
    context_json = json.dumps(
        build_coordinator_decision_context(facts),
        ensure_ascii=False,
        indent=2,
    )
    return f"""你是 AgentHarness Coordinator。你负责判断当前任务是否应该自动推进下一步。

硬性规则：
1. 只能从 candidate_actions 中选择 selected_action_id。
2. 如果 candidate_actions 为空，必须 decision=stop，selected_action_id=null。
3. 如果存在 gate，必须 decision=stop，不能越过 Human Supervisor。
4. 如果 activity.state 是 AGENT_RUNNING，必须 decision=stop，等待 agent 完成。
5. 如果证据矛盾、不确定、agent 输出显示失败风险，必须 decision=stop。
6. 你不能执行 shell 命令，不能修改数据库，不能修改外部项目文件。
7. 只输出一个 JSON object，不要输出 Markdown、代码块或额外文字。

JSON 结构：
{COORDINATOR_DECISION_JSON_SCHEMA}

CONTEXT:
{context_json}
"""


async def generate_coordinator_decision(facts: GeminiTaskFacts) -> CoordinatorDecisionResult:
    response = await generate_gemini_text(build_coordinator_decision_prompt(facts))
    decision = parse_coordinator_decision_json(response.text)
    validation_errors = validate_coordinator_decision(decision, facts)
    return CoordinatorDecisionResult(
        model=response.model,
        facts_version=facts.facts_version,
        decision=decision,
        validation_errors=validation_errors,
    )


def parse_coordinator_decision_json(text: str) -> CoordinatorDecision:
    candidate = strip_json_fence(text.strip())
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if not match:
            raise HTTPException(status_code=502, detail="Coordinator decision response was not JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Coordinator decision response contained invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Coordinator decision JSON must be an object")
    try:
        return CoordinatorDecision.model_validate(parsed)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Coordinator decision JSON did not match schema") from exc


def validate_coordinator_decision(
    decision: CoordinatorDecision,
    facts: GeminiTaskFacts,
) -> list[str]:
    errors: list[str] = []
    candidates = {action.action_id: action for action in safe_candidate_actions(facts)}

    if facts.task.mode != TaskMode.COORDINATOR:
        errors.append("当前任务不是 Coordinator 模式，不能自动推进。")
    if facts.current_gate is not None and facts.current_gate.blocks_auto_advance:
        errors.append("当前存在 Human Supervisor gate，不能自动推进。")
    if facts.workflow_guidance.activity.state == WorkflowActivityState.AGENT_RUNNING:
        errors.append("当前已有 Agent 正在运行，不能自动推进。")

    if decision.decision == "stop":
        if decision.selected_action_id is not None:
            errors.append("decision=stop 时 selected_action_id 必须为 null。")
        return errors

    if not decision.selected_action_id:
        errors.append("decision=continue 时必须提供 selected_action_id。")
        return errors
    if decision.selected_action_id not in candidates:
        errors.append(f"selected_action_id 不在安全候选动作中：{decision.selected_action_id}")
    return errors


def strip_json_fence(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text

