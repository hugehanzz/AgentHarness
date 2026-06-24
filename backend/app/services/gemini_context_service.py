from app.schemas.gemini import GeminiTaskFacts


def build_gemini_task_context(facts: GeminiTaskFacts) -> dict:
    """Return the user-facing facts shared by Gemini brief and task chat."""
    guidance = facts.workflow_guidance
    return {
        "task": {
            "title": facts.task.title,
            "description": facts.task.description,
            "mode": facts.task.mode.value,
        },
        "workflow": {
            "stage": guidance.current_stage_label,
            "status": guidance.current_status_label,
            "position": guidance.current_position,
            "activity": guidance.activity.message,
        },
        "gate": facts.current_gate.model_dump(mode="json") if facts.current_gate else None,
        "actions": [
            {
                "label": action.label,
                "enabled": action.enabled,
                "recommended": action.recommended,
                "requires_human_gate": action.requires_human_gate,
                "instruction": action.instruction,
                "side_effects": action.side_effects,
                "blocked_reason": action.blocked_reason,
            }
            for action in guidance.available_user_actions
        ],
        "review": facts.review_summary.model_dump(mode="json"),
        "recent_agent_results": [
            {
                "status": run.status.value,
                "output_excerpt": run.output_excerpt,
                "error_message": run.error_message,
            }
            for run in facts.latest_agent_runs[:3]
        ],
        "recent_command_results": [
            {
                "status": command.status.value,
                "exit_code": command.exit_code,
            }
            for command in facts.recent_commands[:3]
        ],
    }
