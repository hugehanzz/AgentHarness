from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import gemini_service
from app.services.gemini_service import (
    build_gemini_openai_base_url,
    extract_openai_text,
    generate_gemini_text,
    resolve_gemini_base_url,
)


def test_build_gemini_openai_base_url_trims_base_url():
    assert build_gemini_openai_base_url("https://gemini.example.com/") == "https://gemini.example.com/v1beta/openai/"


def test_generate_gemini_text_requires_base_url(monkeypatch):
    monkeypatch.setattr(
        gemini_service,
        "get_settings",
        lambda: SimpleNamespace(
            google_gemini_base_url=None,
            gemini_openai_base_url="https://generativelanguage.googleapis.com",
            gemini_proxy_url=None,
            gemini_api_key="key",
            gemini_model="gemini-3.1-flash-lite",
            gemini_timeout_seconds=10,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(generate_gemini_text("hello"))

    assert exc_info.value.status_code == 400
    assert "GOOGLE_GEMINI_BASE_URL" in exc_info.value.detail


def test_resolve_gemini_base_url_uses_official_endpoint_when_proxy_is_configured():
    assert (
        resolve_gemini_base_url(
            "http://127.0.0.1:7890",
            None,
            "https://generativelanguage.googleapis.com",
        )
        == "https://generativelanguage.googleapis.com"
    )


def test_generate_gemini_text_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        gemini_service,
        "get_settings",
        lambda: SimpleNamespace(
            google_gemini_base_url="https://gemini.example.com",
            gemini_openai_base_url="https://generativelanguage.googleapis.com",
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


def test_extract_openai_text_reads_first_choice_text():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="OK"),
                finish_reason="stop",
            )
        ]
    )
    text, finish_reason = extract_openai_text(response)

    assert text == "OK"
    assert finish_reason == "stop"


def test_extract_openai_text_rejects_missing_choices():
    with pytest.raises(HTTPException) as exc_info:
        extract_openai_text(SimpleNamespace())

    assert exc_info.value.status_code == 502
    assert "choices" in exc_info.value.detail
