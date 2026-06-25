import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.services import gemini_service
from app.services.gemini_service import (
    build_gemini_native_model_url,
    build_gemini_native_payload,
    extract_native_text,
    generate_gemini_text,
    resolve_gemini_base_url,
)


def test_build_gemini_native_model_url_targets_model_action():
    assert (
        build_gemini_native_model_url("https://generativelanguage.googleapis.com/", "models/gemini-test", "generateContent")
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    )


def test_build_gemini_native_payload_uses_user_content():
    payload = build_gemini_native_payload("hello")

    assert payload["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
    assert payload["generationConfig"]["maxOutputTokens"] == 2048


def test_resolve_gemini_base_url_uses_default_native_endpoint():
    assert (
        resolve_gemini_base_url("https://generativelanguage.googleapis.com/")
        == "https://generativelanguage.googleapis.com"
    )


def test_resolve_gemini_base_url_allows_legacy_google_base_url_override():
    assert (
        resolve_gemini_base_url(
            "https://generativelanguage.googleapis.com",
            "https://gemini.example.com/",
        )
        == "https://gemini.example.com"
    )


def test_generate_gemini_text_requires_api_key(monkeypatch):
    marked_offline = []
    monkeypatch.setattr(gemini_service, "mark_gemini_offline", lambda: marked_offline.append(True))
    monkeypatch.setattr(
        gemini_service,
        "get_settings",
        lambda: SimpleNamespace(
            gemini_base_url="https://generativelanguage.googleapis.com",
            google_gemini_base_url=None,
            gemini_proxy_url=None,
            gemini_api_key=None,
            gemini_model="gemini-3.1-flash-lite",
            gemini_timeout_seconds=10,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(generate_gemini_text("hello"))

    assert exc_info.value.status_code == 400
    assert "GEMINI_API_KEY" in exc_info.value.detail
    assert marked_offline == [True]


def test_extract_native_text_reads_candidate_parts():
    response = {
        "candidates": [
            {
                "content": {"parts": [{"text": "O"}, {"text": "K"}]},
                "finishReason": "STOP",
            }
        ]
    }
    text, finish_reason = extract_native_text(response)

    assert text == "OK"
    assert finish_reason == "STOP"


def test_extract_native_text_rejects_missing_text():
    with pytest.raises(HTTPException) as exc_info:
        extract_native_text({})

    assert exc_info.value.status_code == 502
    assert "text" in exc_info.value.detail
