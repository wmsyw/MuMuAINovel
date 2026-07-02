from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.settings import _sanitize_settings_urls, resolve_runtime_ai_config


def test_settings_url_sanitizer_rejects_loopback_base_url() -> None:
    with pytest.raises(HTTPException):
        _sanitize_settings_urls({"api_base_url": "http://127.0.0.1:8000/v1"})


def test_settings_url_sanitizer_normalizes_public_base_urls() -> None:
    sanitized = _sanitize_settings_urls(
        {
            "api_base_url": "https://1.1.1.1/v1/",
            "cover_api_base_url": "https://8.8.8.8/v1/",
        }
    )

    assert sanitized["api_base_url"] == "https://1.1.1.1/v1"
    assert sanitized["cover_api_base_url"] == "https://8.8.8.8/v1"


def test_runtime_ai_config_revalidates_stored_base_url() -> None:
    with pytest.raises(HTTPException):
        resolve_runtime_ai_config("openai", "test-key", "http://localhost:11434/v1")
