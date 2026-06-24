from app.schemas.gemini import (
    GeminiAgentRunFact,
    GeminiChatMessage,
    GeminiChatRequest,
    GeminiCommandRunFact,
    GeminiEventFact,
    GeminiGateFact,
    GeminiReviewSummary,
    GeminiTaskFact,
    GeminiTaskFacts,
    GeminiWorkflowGuidance,
)
from app.core.state_machine import TaskStatus
from app.models.command import CommandStatus
from app.models.task import TaskMode
from app.models.worker import RunStatus
from app.schemas.workflow import WorkflowActivity, WorkflowActivityState
from app.services.gemini_chat_service import (
    build_home_chat_messages,
    build_native_payload,
    build_native_stream_url,
    build_task_chat_messages,
    extract_native_stream_text,
    normalize_history,
    parse_native_sse_line,
    split_text_delta,
    sse_event,
)


def make_payload() -> GeminiChatRequest:
    return GeminiChatRequest(
        message="现在卡在哪里？",
        history=[
            GeminiChatMessage(role="user", content="你好"),
            GeminiChatMessage(role="assistant", content="你好，我是 Gemini"),
        ],
    )


def make_facts() -> GeminiTaskFacts:
    return GeminiTaskFacts(
        facts_version="abc123",
        task=GeminiTaskFact(
            id=1,
            title="测试任务",
            description="实现一个功能",
            workspace_path="D:/workspace",
            status=TaskStatus.ACCEPTANCE_READY,
            mode=TaskMode.SECRETARY,
        ),
        current_gate=GeminiGateFact(
            type="ACCEPTANCE",
            owner="Human Supervisor",
            reason="等待人工验收",
        ),
        workflow_guidance=GeminiWorkflowGuidance(
            current_stage_label="Accept",
            current_status_label="待验收",
            current_position="任务已经准备好进入人工验收。",
            activity=WorkflowActivity(
                state=WorkflowActivityState.WAITING_FOR_HUMAN_GATE,
                message="当前流程正在等待 Human Supervisor 确认。",
            ),
            available_user_actions=[],
        ),
        recent_events=[
            GeminiEventFact(
                event_type="STATE_CHANGED",
                from_status=TaskStatus.RECHECK_DONE,
                to_status=TaskStatus.ACCEPTANCE_READY,
                message="ready",
                created_by="system",
                created_at="2026-06-21T00:00:00",
            )
        ],
        latest_agent_runs=[
            GeminiAgentRunFact(
                id=1,
                run_type="CODEX",
                provider_type="CODEX",
                status=RunStatus.SUCCEEDED,
                output_excerpt="done",
                error_message=None,
                finished_at="2026-06-21T00:00:00",
                created_at="2026-06-21T00:00:00",
            )
        ],
        review_summary=GeminiReviewSummary(
            total_count=0,
            open_count=0,
            high_open_count=0,
            medium_open_count=0,
            low_open_count=0,
            unknown_open_count=0,
            open_items=[],
        ),
        recent_commands=[
            GeminiCommandRunFact(
                id=1,
                command_key="pytest",
                status=CommandStatus.SUCCEEDED,
                exit_code=0,
                duration_ms=100,
                created_at="2026-06-21T00:00:00",
            )
        ],
    )


def test_sse_event_formats_json_payload():
    assert sse_event("delta", {"text": "你好"}) == 'event: delta\ndata: {"text": "你好"}\n\n'


def test_split_text_delta_breaks_large_delta_for_progressive_display():
    assert split_text_delta("abcdefghijkl", chunk_size=5) == ["abcde", "fghij", "kl"]


def test_normalize_history_keeps_supported_roles():
    history = normalize_history(make_payload())

    assert history == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，我是 Gemini"},
    ]


def test_build_home_chat_messages_includes_guardrails():
    messages = build_home_chat_messages(make_payload())

    assert messages[0]["role"] == "system"
    assert "不能确认计划" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "现在卡在哪里？"}


def test_build_task_chat_messages_includes_facts_and_guardrails():
    messages = build_task_chat_messages(make_facts(), make_payload())

    assert messages[0]["role"] == "system"
    assert "CURRENT_TASK_FACTS" in messages[0]["content"]
    assert "ACCEPTANCE_READY" not in messages[0]["content"]
    assert "workspace_path" not in messages[0]["content"]
    assert "provider_type" not in messages[0]["content"]
    assert "等待人工验收" in messages[0]["content"]
    assert "不能批准验收" in messages[0]["content"]


def test_build_native_stream_url_targets_stream_generate_content():
    assert (
        build_native_stream_url("https://generativelanguage.googleapis.com/", "models/gemini-test")
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:streamGenerateContent"
    )


def test_build_native_payload_maps_chat_roles_to_gemini_roles():
    payload = build_native_payload(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
    )

    assert payload["systemInstruction"] == {"parts": [{"text": "system prompt"}]}
    assert payload["contents"] == [
        {"role": "user", "parts": [{"text": "hello"}]},
        {"role": "model", "parts": [{"text": "hi"}]},
    ]
    assert payload["generationConfig"]["maxOutputTokens"] == 512


def test_extract_native_stream_text_reads_candidate_parts():
    payload = {"candidates": [{"content": {"parts": [{"text": "O"}, {"text": "K"}]}}]}

    assert extract_native_stream_text(payload) == "OK"


def test_parse_native_sse_line_reads_data_json():
    assert parse_native_sse_line('data: {"candidates": []}') == {"candidates": []}
