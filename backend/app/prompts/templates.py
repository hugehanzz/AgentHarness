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
        PromptType.CODEX_PLAN: "产出实现计划。当前阶段不要修改任何文件。请说明依赖变更、迁移事项、风险点，以及需要 Human Supervisor 审批的门禁。",
        PromptType.CODEX_IMPLEMENT: "按照已确认的计划执行开发，运行相关测试。",
        PromptType.CLAUDE_REVIEW: "评审Codex的本次代码实现并维护 REVIEW.md。按 High、Medium、Low 严重级别归类问题，并包含开放事项和复查结论。",
        PromptType.CODEX_FIX: "读取 REVIEW.md，修复Claude审查的问题，运行相关验证，并总结变更内容。不要修改 REVIEW.md。",
        PromptType.CLAUDE_RECHECK: (
            "复查修复结果，并在 REVIEW.md 中更新复查结论。"
            "若复查通过，根据 CLAUDE.md 的 REVIEW.md 维护规范执行历史审查归档。"
            "即使本轮没有 Codex 修复项，也要根据维护规范执行封版，"
            "同步更新机器可读状态，并明确是否可以进入验收。"
        ),
        PromptType.ACCEPTANCE_CHECKLIST: (
            "为 Human Supervisor 生成面向人工操作的验收建议。不要替人类宣布验收通过。"
            "请根据任务需求、实现阶段输出、REVIEW.md/复审结论、测试或命令证据，给出具体可执行的验收方式："
            "如果涉及前端，请说明应打开哪个页面、点击哪些控件、输入什么数据、观察什么状态；"
            "如果涉及 API，请给出适合 Apifox/Postman/curl 的方法、地址、请求体示例和期望响应；"
            "如果涉及后端逻辑或文档，请说明应运行哪些命令、查看哪些文件或日志。"
            "最后列出通过标准和打回标准，帮助 Human Supervisor 做最终决定。"
        ),
        PromptType.README_ARCHIVE: "根据本次任务的实际变更，判断是否需要更新相关 README，使 README 反映项目当前事实状态。如果本次任务改变了项目功能、使用方式、开发或测试方式、架构说明、模块状态、已知限制或运维说明，请优先维护现有章节；只有现有结构无法表达新事实时，才新增章节。如果本次任务没有改变 README 应记录的当前事实，可以不修改 README。不要追加任务流水账、验收记录或“任务归档记录”章节。不要修改 REVIEW.md。",
    }

    return f"""{base}
输出语言：
请使用简体中文回复。代码标识符、文件路径、命令、异常信息和原始日志可以保持原文。

指令：
{templates[prompt_type]}
"""
