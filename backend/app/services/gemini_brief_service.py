import json
import re

from fastapi import HTTPException

from app.core.state_machine import TaskStatus
from app.schemas.gemini import GeminiTaskBrief, GeminiTaskFacts
from app.schemas.workflow import WorkflowActivityState
from app.services.gemini_context_service import build_gemini_task_context
from app.services.gemini_service import generate_gemini_text


MAX_GENERATION_ATTEMPTS = 2
INTERNAL_TERMS = tuple(status.value for status in TaskStatus)
AGENT_RUN_BUTTON_LABELS = {
    "codex_plan": "运行 Codex Plan",
    "codex_implement": "运行 Codex Implement",
    "claude_review": "运行 Claude Review",
    "codex_fix": "运行 Codex Fix",
    "claude_recheck": "运行 Claude Recheck",
    "claude_finalize": "审查封板",
    "codex_acceptance_checklist": "Codex 给出验收方案",
    "codex_archive": "运行 Codex Archive",
}

BRIEF_JSON_SCHEMA = """{
  "summary": "string, concise Chinese summary of current task progress",
  "current_position": "string, Chinese explanation of current workflow position",
  "pending_gate": null or {
    "type": "string",
    "owner": "string",
    "reason": "string",
    "blocks_auto_advance": true
  },
  "suggested_next_steps": ["string"],
  "risk_notes": ["string"]
}"""


def build_gemini_secretary_prompt(facts: GeminiTaskFacts) -> str:
    context_json = json.dumps(
        build_gemini_brief_context(facts),
        ensure_ascii=False,
        indent=2,
    )
    return f"""你是 AgentHarness 的只读 Gemini 秘书。仅根据 CONTEXT 生成面向用户的任务简报。

规则：
1. 使用简体中文，不展示内部枚举、action_id 或 run_type。
2. 下一步只使用 actions 中的真实按钮名称。
3. 优先建议 enabled=true 且 recommended=true 的动作；没有推荐动作时才使用其他已启用动作。
4. enabled=false 的动作只能解释 blocked_reason，不能建议点击。
5. 点击结果只能复述 side_effects，不得声称已经执行、批准或完成未发生的流程。
6. pending_gate 必须原样使用 gate；gate 为 null 时也必须输出 null。Gemini 不能代替人工批准。
7. 只输出一个 JSON object，不要输出 Markdown、代码块或额外文字。

JSON 结构：
{BRIEF_JSON_SCHEMA}

CONTEXT:
{context_json}
"""


def build_gemini_brief_context(facts: GeminiTaskFacts) -> dict:
    context = build_gemini_task_context(facts)
    label = active_agent_button_label(facts)
    if label:
        context["active_agent_button"] = {
            "label": label,
            "enabled": True,
            "instruction": f"点击「{label}」继续当前流程。",
        }
    return context


async def generate_gemini_task_brief(facts: GeminiTaskFacts) -> GeminiTaskBrief:
    prompt = build_gemini_secretary_prompt(facts)
    last_model = "backend-fallback"
    validation_errors: list[str] = []

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        retry_prompt = prompt
        if validation_errors:
            retry_prompt += build_validation_retry_instruction(validation_errors)

        response = await generate_gemini_text(retry_prompt)
        last_model = response.model
        try:
            payload = parse_gemini_brief_json(response.text)
            brief = build_brief(payload, facts, response.model)
        except (HTTPException, ValueError) as exc:
            validation_errors = [str(getattr(exc, "detail", exc))]
            continue

        validation_errors = validate_gemini_brief(brief, facts)
        if not validation_errors:
            return brief

    return build_fallback_brief(facts, last_model)


def build_brief(payload: dict, facts: GeminiTaskFacts, model: str) -> GeminiTaskBrief:
    payload["ok"] = True
    payload["model"] = model
    payload["facts_version"] = facts.facts_version
    return GeminiTaskBrief.model_validate(payload)


def validate_gemini_brief(
    brief: GeminiTaskBrief,
    facts: GeminiTaskFacts,
) -> list[str]:
    errors: list[str] = []
    all_text = "\n".join(
        [
            brief.summary,
            brief.current_position,
            *brief.suggested_next_steps,
            *brief.risk_notes,
        ]
    )
    exposed_terms = [term for term in INTERNAL_TERMS if term in all_text]
    if exposed_terms:
        errors.append(f"不得向用户展示内部状态枚举：{', '.join(exposed_terms)}")

    actions = facts.workflow_guidance.available_user_actions
    enabled_actions = [action for action in actions if action.enabled]
    disabled_actions = [action for action in actions if not action.enabled]
    recommended_actions = [action for action in enabled_actions if action.recommended]
    active_button_label = active_agent_button_label(facts)
    steps_text = "\n".join(brief.suggested_next_steps)

    for action in disabled_actions:
        if action.label in steps_text and contains_click_instruction(steps_text):
            errors.append(f"不得建议点击尚未启用的按钮「{action.label}」")

    expected_actions = recommended_actions or enabled_actions
    if expected_actions and not any(action.label in steps_text for action in expected_actions):
        labels = "、".join(f"「{action.label}」" for action in expected_actions)
        errors.append(f"下一步建议必须使用后端提供的按钮名称：{labels}")
    if not expected_actions and active_button_label and active_button_label not in steps_text:
        errors.append(f"下一步建议必须使用当前可见的 Agent 按钮名称：「{active_button_label}」")

    if recommended_actions:
        non_recommended_actions = [
            action for action in enabled_actions if not action.recommended
        ]
        for action in non_recommended_actions:
            if action.label in steps_text and contains_click_instruction(steps_text):
                errors.append(f"已有更合适的推荐动作，不应同时建议点击「{action.label}」")

    if not enabled_actions and any(action.label in steps_text for action in actions):
        errors.append("当前没有可用按钮，不得建议用户点击流程按钮")
    if "REVIEW.md" in all_text and any(keyword in all_text for keyword in ("手动", "修改", "更新", "同步")):
        errors.append("Gemini 不得建议用户手动修改 REVIEW.md；REVIEW.md 由 Claude 维护")

    mentioned_actions = [action for action in actions if action.label in steps_text]
    if (
        any(keyword in steps_text for keyword in ("完成任务", "任务完成"))
        and not any(action.to_status == TaskStatus.DONE for action in mentioned_actions)
    ):
        errors.append("当前动作不会完成整个任务，不得声称点击后任务完成")

    if facts.current_gate is None and brief.pending_gate is not None:
        errors.append("当前不存在人工门禁，pending_gate 必须为 null")
    if facts.current_gate is not None:
        if brief.pending_gate is None:
            errors.append("当前存在人工门禁，必须在 pending_gate 中说明")
        elif (
            brief.pending_gate.type != facts.current_gate.type
            or brief.pending_gate.owner != facts.current_gate.owner
        ):
            errors.append("pending_gate 必须与后端事实一致")
    return errors


def contains_click_instruction(text: str) -> bool:
    return any(keyword in text for keyword in ("点击", "按下", "选择", "执行"))


def build_validation_retry_instruction(errors: list[str]) -> str:
    error_text = "\n".join(f"- {error}" for error in errors)
    return f"""

你上一次的输出未通过后端校验，请重新生成完整 JSON。
必须修正：
{error_text}
"""


def build_fallback_brief(
    facts: GeminiTaskFacts,
    model: str,
) -> GeminiTaskBrief:
    guidance = facts.workflow_guidance
    active_button_label = active_agent_button_label(facts)
    enabled_actions = [action for action in guidance.available_user_actions if action.enabled]
    recommended_actions = [action for action in enabled_actions if action.recommended]
    selected_actions = recommended_actions or enabled_actions

    if active_button_label:
        suggested_next_steps = [f"点击「{active_button_label}」继续当前流程。"]
    elif guidance.activity.state == WorkflowActivityState.AGENT_RUNNING:
        suggested_next_steps = [guidance.activity.message]
    elif selected_actions:
        suggested_next_steps = [action.instruction for action in selected_actions]
    else:
        blocked_reasons = [
            action.blocked_reason
            for action in guidance.available_user_actions
            if action.blocked_reason
        ]
        suggested_next_steps = blocked_reasons or ["当前没有需要执行的下一步操作。"]

    risk_notes = [
        action.blocked_reason
        for action in guidance.available_user_actions
        if action.blocked_reason
    ]
    if facts.current_gate is not None:
        risk_notes.append(facts.current_gate.reason)

    return GeminiTaskBrief(
        ok=True,
        model=model,
        facts_version=facts.facts_version,
        summary=f"任务当前处于“{guidance.current_status_label}”状态。",
        current_position=guidance.current_position,
        pending_gate=facts.current_gate,
        suggested_next_steps=list(dict.fromkeys(suggested_next_steps)),
        risk_notes=list(dict.fromkeys(risk_notes)),
    )


def active_agent_button_label(facts: GeminiTaskFacts) -> str | None:
    activity = facts.workflow_guidance.activity
    if activity.state not in {WorkflowActivityState.WAITING_FOR_USER, WorkflowActivityState.AGENT_FAILED}:
        return None
    if not activity.agent_run_type:
        return None
    return AGENT_RUN_BUTTON_LABELS.get(activity.agent_run_type)


def parse_gemini_brief_json(text: str) -> dict:
    candidate = strip_json_fence(text.strip())
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if not match:
            raise HTTPException(status_code=502, detail="Gemini brief response was not JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Gemini brief response contained invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Gemini brief response JSON must be an object")
    return parsed


def strip_json_fence(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text
