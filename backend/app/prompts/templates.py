from app.models.prompt import PromptType
from app.models.task import Task


def build_prompt(task: Task, prompt_type: PromptType) -> str:
    base = f"""项目：AgentHarness 托管工作区
任务 ID：{task.id}
任务标题：{task.title}
当前状态：{task.status}
工作区路径：{task.workspace_path or "未提供"}

需求：
{task.description}
"""

    templates = {
        PromptType.CODEX_PLAN: "请产出实现计划。当前阶段不要修改任何文件。请说明依赖变更、迁移事项、风险点，以及需要 Human Supervisor 审批的门禁。",
        PromptType.CODEX_IMPLEMENT: "请按照已确认的计划执行开发，运行相关测试，并在确有必要时更新相关 README。不要绕过 Human Supervisor 门禁。",
        PromptType.CLAUDE_REVIEW: "请评审本次实现并维护 REVIEW.md。请按 High、Medium、Low 严重级别归类问题，并包含开放事项和复查结论。",
        PromptType.CODEX_FIX: "请读取 REVIEW.md，修复其中仍开放的问题，运行相关验证，并总结变更内容。不要修改 REVIEW.md。",
        PromptType.CLAUDE_RECHECK: "请复查修复结果，并在 REVIEW.md 中更新复查结论。请明确是否可以进入验收。",
        PromptType.ACCEPTANCE_CHECKLIST: "请生成 Human Supervisor 验收清单，包含证据字段和可自动检查的项目。",
        PromptType.README_ARCHIVE: "在 Human Supervisor 批准后，请由 Codex 更新相关 README，包括根目录、前端、后端、App 端和数据库文档中与本任务相关的归档内容；记录验收状态、验证结果、归档说明和后续建议。不要修改 REVIEW.md。",
    }

    return f"""{base}
输出语言：
请使用简体中文回复。代码标识符、文件路径、命令、异常信息和原始日志可以保持原文。

指令：
{templates[prompt_type]}
"""
