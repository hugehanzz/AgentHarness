from app.models.prompt import PromptType
from app.models.task import Task


def build_prompt(task: Task, prompt_type: PromptType) -> str:
    base = f"""Project: AgentHarness managed workspace
Task ID: {task.id}
Task Title: {task.title}
Current Status: {task.status}
Workspace Path: {task.workspace_path or "Not provided"}

Requirement:
{task.description}
"""

    templates = {
        PromptType.CODEX_PLAN: "Please produce an implementation plan. Do not modify files yet. Call out dependencies, migrations, risks, and required Human Supervisor gates.",
        PromptType.CODEX_IMPLEMENT: "Please implement the confirmed plan, run relevant tests, and update README where appropriate. Do not bypass Human Supervisor gates.",
        PromptType.CLAUDE_REVIEW: "Please review the implementation and maintain REVIEW.md. Group issues by High, Medium, and Low severity. Include open items and recheck conclusion.",
        PromptType.CODEX_FIX: "Please read REVIEW.md, fix open issues, run relevant verification, and summarize what changed. Do not modify REVIEW.md.",
        PromptType.CLAUDE_RECHECK: "Please recheck the fixes and update REVIEW.md with the recheck conclusion. Mark whether acceptance can proceed.",
        PromptType.ACCEPTANCE_CHECKLIST: "Please generate a Human Supervisor acceptance checklist with evidence fields and any auto-checkable items.",
        PromptType.README_ARCHIVE: "Please update README with acceptance status, verification results, archive notes, and next-step suggestions after Human Supervisor approval.",
    }

    return f"{base}\nInstruction:\n{templates[prompt_type]}\n"
