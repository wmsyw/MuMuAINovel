from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.cover_generation_service import CoverGenerationService
from app.services.cover_providers.gemini_cover_provider import GeminiCoverProvider
from app.services.cover_providers.grok_cover_provider import GrokCoverProvider
from app.services.cover_providers.openai_image_cover_provider import OpenAIImageCoverProvider


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


def test_provider_factory_routes_mumu_v1beta_to_gemini() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="mumu",
        api_key="key",
        api_base_url="https://api.mumuverse.space/v1beta",
        model="gemini-2.5-flash-image-preview",
    )

    assert isinstance(provider, GeminiCoverProvider)


def test_provider_factory_routes_mumu_v1_gpt_image_to_openai_format() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="mumu",
        api_key="key",
        api_base_url="https://api.mumuverse.space/v1",
        model="gpt-image-2",
    )

    assert isinstance(provider, OpenAIImageCoverProvider)
    assert provider.base_url == "https://api.mumuverse.space/v1"


def test_provider_factory_routes_empty_mumu_gpt_image_to_default_mumu_openai_format() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="mumu",
        api_key="key",
        api_base_url="",
        model="gpt-image-2",
    )

    assert isinstance(provider, OpenAIImageCoverProvider)
    assert provider.base_url == "https://api.mumuverse.space/v1"


def test_provider_factory_keeps_mumu_v1_non_gpt_image_on_grok_format() -> None:
    service = CoverGenerationService()

    provider = service._build_provider_from_values(
        provider="mumu",
        api_key="key",
        api_base_url="https://api.mumuverse.space/v1",
        model="grok-2-image",
    )

    assert isinstance(provider, GrokCoverProvider)


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
