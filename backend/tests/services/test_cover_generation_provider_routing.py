from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.cover_generation_service import CoverGenerationService
from app.services.cover_providers.openai_image_cover_provider import OpenAIImageCoverProvider
from app.services.cover_providers.gemini_cover_provider import GeminiCoverProvider
from app.services.cover_providers.grok_cover_provider import GrokCoverProvider


def test_provider_factory_returns_openai_image_provider_for_openai() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="openai",
        api_key="key",
        api_base_url="",
        model="gpt-image-2",
    )

    assert isinstance(provider, OpenAIImageCoverProvider)
    assert provider.base_url == "https://api.openai.com/v1"
def test_provider_factory_uses_generic_openai_default_for_legacy_empty_base_url() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="mumu",
        api_key="key",
        api_base_url="",
        model="gpt-image-2",
    )

    assert isinstance(provider, OpenAIImageCoverProvider)
    assert provider.base_url == "https://api.openai.com/v1"


def test_provider_factory_normalizes_custom_openai_compatible_provider() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="custom",
        api_key="key",
        api_base_url="https://gateway.example/v1",
        model="image-model",
    )

    assert isinstance(provider, OpenAIImageCoverProvider)
    assert provider.base_url == "https://gateway.example/v1"

def test_provider_factory_normalizes_legacy_gemini_cover_settings() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider=" MUMU ",
        api_key="key",
        api_base_url="https://gateway.example/v1beta/",
        model="gemini-3.1-flash-image-preview",
    )

    assert isinstance(provider, GeminiCoverProvider)
    assert provider.base_url == "https://gateway.example/v1beta"


def test_provider_factory_preserves_legacy_openai_compatible_gateway() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="mumu",
        api_key="key",
        api_base_url="https://gateway.example/v1/",
        model="image-model",
    )

    assert isinstance(provider, OpenAIImageCoverProvider)
    assert provider.base_url == "https://gateway.example/v1"


def test_provider_factory_normalizes_legacy_grok_cover_settings() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="mumu",
        api_key="key",
        api_base_url="https://api.x.ai/v1",
        model="grok-2-image",
    )

    assert isinstance(provider, GrokCoverProvider)


def test_provider_factory_rejects_ambiguous_legacy_settings() -> None:
    service = CoverGenerationService()

    with pytest.raises(HTTPException) as exc_info:
        service._build_provider_from_values(
            provider="mumu",
            api_key="key",
            api_base_url="",
            model="image-model",
        )

    assert exc_info.value.status_code == 400
    assert "已过期" in str(exc_info.value.detail)


def test_provider_factory_unsupported_provider_mentions_openai() -> None:
    service = CoverGenerationService()

    with pytest.raises(HTTPException) as exc_info:
        service._build_provider_from_values(
            provider="unknown",
            api_key="key",
            api_base_url="https://api.example.com/v1",
            model="gpt-image-2",
        )

    assert exc_info.value.status_code == 400
    assert "OpenAI" in str(exc_info.value.detail)
