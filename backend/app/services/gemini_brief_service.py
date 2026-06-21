import json
import re

from fastapi import HTTPException

from app.schemas.gemini import GeminiTaskBrief, GeminiTaskFacts
from app.services.gemini_service import generate_gemini_text


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
    facts_json = facts.model_dump_json(indent=2)
    return f"""你是 AgentHarness 的 Gemini Secretary，是系统内部只读 AI 秘书。

你的职责：
- 总结当前任务进度。
- 解释任务当前处于哪个流程位置。
- 提醒 Human Supervisor 是否存在 pending gate。
- 根据 backend 提供的 safe_next_actions 给出安全下一步建议。
- 提醒风险和边界。

严格限制：
- 你不能声称已经推进状态。
- 你不能批准计划。
- 你不能批准最终验收。
- 你不能安装依赖。
- 你不能执行命令。
- 你不能修改外部业务项目代码。
- 你不能绕过 Human Supervisor gate。
- 你只能基于下面的 task facts 回答，不能编造系统中不存在的事实。

输出要求：
- 只输出一个 JSON object。
- 不要输出 Markdown。
- 不要输出代码块。
- 不要输出 JSON 外的解释文字。
- 使用简体中文。
- JSON 结构必须符合：
{BRIEF_JSON_SCHEMA}

task facts:
{facts_json}
"""


async def generate_gemini_task_brief(facts: GeminiTaskFacts) -> GeminiTaskBrief:
    response = await generate_gemini_text(build_gemini_secretary_prompt(facts))
    payload = parse_gemini_brief_json(response.text)
    payload["ok"] = True
    payload["model"] = response.model
    payload["facts_version"] = facts.facts_version
    return GeminiTaskBrief.model_validate(payload)


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
