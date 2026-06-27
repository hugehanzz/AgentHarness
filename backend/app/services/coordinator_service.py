import json
import re

from fastapi import HTTPException

from app.core.state_machine import TaskStatus
from app.core.workflow_actions import AgentRunTiming
from app.models.task import TaskMode
from app.models.worker import RunStatus
from app.schemas.coordinator import (
    CoordinatorActionValidation,
    CoordinatorDecision,
    CoordinatorDecisionResult,
    CoordinatorRunResult,
    CoordinatorStepResult,
)
from app.schemas.gemini import GeminiTaskFacts
from app.schemas.workflow import ResolvedWorkflowAction, WorkflowActivityState
from app.services.agent_run_service import run_agent
from app.services.gemini_facts_service import build_gemini_task_facts
from app.services.gemini_service import generate_gemini_text
from app.services.task_service import get_task_or_404, transition_task


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


def validate_coordinator_action_selection(
    facts: GeminiTaskFacts,
    selected_action_id: str | None,
) -> CoordinatorActionValidation:
    errors: list[str] = []
    action_by_id = {
        action.action_id: action
        for action in facts.workflow_guidance.available_user_actions
    }
    selected_action = action_by_id.get(selected_action_id) if selected_action_id else None

    if facts.task.mode != TaskMode.COORDINATOR:
        errors.append("当前任务不是 Coordinator 模式，不能自动推进。")
    if facts.current_gate is not None and facts.current_gate.blocks_auto_advance:
        errors.append("当前存在 Human Supervisor gate，不能自动推进。")
    if facts.workflow_guidance.activity.state == WorkflowActivityState.AGENT_RUNNING:
        errors.append("当前已有 Agent 正在运行，不能自动推进。")
    if not selected_action_id:
        errors.append("缺少 selected_action_id，不能自动推进。")
        return CoordinatorActionValidation(allowed=False, action=None, errors=errors)
    if selected_action is None:
        errors.append(f"selected_action_id 不属于当前状态的工作流动作：{selected_action_id}")
        return CoordinatorActionValidation(allowed=False, action=None, errors=errors)
    if not selected_action.enabled:
        blocked_reason = selected_action.blocked_reason or "动作当前未启用。"
        errors.append(f"动作「{selected_action.label}」未启用：{blocked_reason}")
    if selected_action.requires_human_gate:
        errors.append(f"动作「{selected_action.label}」需要 Human Supervisor，不能自动执行。")

    return CoordinatorActionValidation(
        allowed=not errors,
        action=selected_action if not errors else None,
        errors=errors,
    )


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


async def run_coordinator_step(session, task_id: int) -> CoordinatorStepResult:
    facts = build_gemini_task_facts(session, task_id)
    status_before = facts.task.status
    acceptance_checklist_step = await run_acceptance_checklist_if_needed(session, task_id, facts)
    if acceptance_checklist_step:
        return acceptance_checklist_step

    preflight_stop = build_preflight_stop_decision(facts)
    if preflight_stop:
        return CoordinatorStepResult(
            executed=False,
            decision=preflight_stop,
            task_status_before=status_before,
            task_status_after=status_before,
            stop_reason=preflight_stop.reason,
        )

    decision_result = await generate_coordinator_decision(facts)
    decision = decision_result.decision
    if decision.decision == "stop":
        return CoordinatorStepResult(
            executed=False,
            decision=decision,
            task_status_before=status_before,
            task_status_after=status_before,
            stop_reason=decision.reason,
            validation_errors=decision_result.validation_errors,
        )

    action_validation = validate_coordinator_action_selection(facts, decision.selected_action_id)
    validation_errors = [*decision_result.validation_errors, *action_validation.errors]
    if validation_errors or action_validation.action is None:
        return CoordinatorStepResult(
            executed=False,
            decision=decision,
            task_status_before=status_before,
            task_status_after=status_before,
            stop_reason="Coordinator decision did not pass backend action validation.",
            validation_errors=validation_errors,
        )

    action = action_validation.action
    agent_run_id: int | None = None
    agent_run_status: RunStatus | None = None

    if action.agent_run_type and action.agent_run_timing == AgentRunTiming.BEFORE_TRANSITION:
        agent_run = await run_agent(session, task_id, action.agent_run_type)
        agent_run_id = agent_run.id
        agent_run_status = agent_run.status
        if agent_run.status != RunStatus.SUCCEEDED:
            return CoordinatorStepResult(
                executed=True,
                decision=decision,
                action_id=action.action_id,
                action_label=action.label,
                task_status_before=status_before,
                task_status_after=get_task_or_404(session, task_id).status,
                agent_run_id=agent_run_id,
                agent_run_status=agent_run_status,
                stop_reason=f"Agent run {action.agent_run_type} did not succeed.",
                validation_errors=validation_errors,
            )

    transition_task(
        session,
        task_id,
        action.to_status,
        f"Gemini Coordinator: {action.label}",
        "gemini_coordinator",
    )

    if action.agent_run_type and action.agent_run_timing == AgentRunTiming.AFTER_TRANSITION:
        agent_run = await run_agent(session, task_id, action.agent_run_type)
        agent_run_id = agent_run.id
        agent_run_status = agent_run.status
        if agent_run.status != RunStatus.SUCCEEDED:
            task_after = get_task_or_404(session, task_id)
            return CoordinatorStepResult(
                executed=True,
                decision=decision,
                action_id=action.action_id,
                action_label=action.label,
                task_status_before=status_before,
                task_status_after=task_after.status,
                agent_run_id=agent_run_id,
                agent_run_status=agent_run_status,
                stop_reason=f"Agent run {action.agent_run_type} did not succeed.",
                validation_errors=validation_errors,
            )

    task_after = get_task_or_404(session, task_id)
    return CoordinatorStepResult(
        executed=True,
        decision=decision,
        action_id=action.action_id,
        action_label=action.label,
        task_status_before=status_before,
        task_status_after=task_after.status,
        agent_run_id=agent_run_id,
        agent_run_status=agent_run_status,
        validation_errors=validation_errors,
    )


async def run_acceptance_checklist_if_needed(
    session,
    task_id: int,
    facts: GeminiTaskFacts,
) -> CoordinatorStepResult | None:
    if facts.task.status != TaskStatus.ACCEPTANCE_READY:
        return None
    if any(
        run.run_type == "codex_acceptance_checklist"
        and run.status == RunStatus.SUCCEEDED
        for run in facts.latest_agent_runs
    ):
        return None

    decision = CoordinatorDecision(
        decision="continue",
        selected_action_id="codex_acceptance_checklist",
        confidence="high",
        reason="先让 Codex 生成验收方案，然后等待 Human Supervisor 标记验收通过。",
        risk_notes=[],
    )
    agent_run = await run_agent(session, task_id, "codex_acceptance_checklist")
    task_after = get_task_or_404(session, task_id)
    stop_reason = (
        "Codex 已生成验收方案，等待 Human Supervisor 标记验收通过。"
        if agent_run.status == RunStatus.SUCCEEDED
        else "Agent run codex_acceptance_checklist did not succeed."
    )
    return CoordinatorStepResult(
        executed=True,
        decision=decision,
        action_id="codex_acceptance_checklist",
        action_label="Codex 给出验收方案",
        task_status_before=facts.task.status,
        task_status_after=task_after.status,
        agent_run_id=agent_run.id,
        agent_run_status=agent_run.status,
        stop_reason=stop_reason,
    )


async def run_coordinator_until_blocked(
    session,
    task_id: int,
    max_steps: int = 10,
) -> CoordinatorRunResult:
    steps: list[CoordinatorStepResult] = []
    executed_steps = 0
    stop_reason: str | None = None

    for _ in range(max(1, max_steps)):
        step = await run_coordinator_step(session, task_id)
        steps.append(step)
        if step.executed:
            executed_steps += 1
        if should_stop_after_step(step):
            stop_reason = step.stop_reason or step.decision.reason
            break
    else:
        stop_reason = f"Reached coordinator max_steps={max_steps}."

    return CoordinatorRunResult(
        executed_steps=executed_steps,
        stopped=True,
        stop_reason=stop_reason,
        steps=steps,
    )


def should_stop_after_step(step: CoordinatorStepResult) -> bool:
    if not step.executed:
        return True
    if step.stop_reason:
        return True
    if step.validation_errors:
        return True
    if step.agent_run_status is not None and step.agent_run_status != RunStatus.SUCCEEDED:
        return True
    if step.task_status_after == step.task_status_before:
        return True
    return False


def build_preflight_stop_decision(facts: GeminiTaskFacts) -> CoordinatorDecision | None:
    if facts.task.status == TaskStatus.DONE:
        return CoordinatorDecision(
            decision="stop",
            selected_action_id=None,
            confidence="high",
            reason="任务流程已经完成。",
            risk_notes=[],
        )
    if facts.task.mode != TaskMode.COORDINATOR:
        return CoordinatorDecision(
            decision="stop",
            selected_action_id=None,
            confidence="high",
            reason="当前任务不是 Coordinator 模式，不能自动推进。",
            risk_notes=[],
        )
    if facts.current_gate is not None and facts.current_gate.blocks_auto_advance:
        return CoordinatorDecision(
            decision="stop",
            selected_action_id=None,
            confidence="high",
            reason=f"当前等待 {facts.current_gate.owner} 处理「{facts.current_gate.type}」。",
            risk_notes=[facts.current_gate.reason],
        )
    if facts.workflow_guidance.activity.state == WorkflowActivityState.AGENT_RUNNING:
        return CoordinatorDecision(
            decision="stop",
            selected_action_id=None,
            confidence="high",
            reason=facts.workflow_guidance.activity.message,
            risk_notes=[],
        )
    if not safe_candidate_actions(facts):
        return CoordinatorDecision(
            decision="stop",
            selected_action_id=None,
            confidence="medium",
            reason="当前没有可安全自动执行的 workflow action。",
            risk_notes=[
                action.blocked_reason
                for action in facts.workflow_guidance.available_user_actions
                if action.blocked_reason
            ],
        )
    return None


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

    if decision.decision == "stop":
        if decision.selected_action_id is not None:
            errors.append("decision=stop 时 selected_action_id 必须为 null。")
        return errors

    action_validation = validate_coordinator_action_selection(facts, decision.selected_action_id)
    errors.extend(action_validation.errors)
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
