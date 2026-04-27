import asyncio
import ast
import json as json_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas.settings import SettingsCreate, SettingsResponse
from app.services.ai_clients.anthropic_client import AnthropicClient
from app.services.ai_clients.gemini_client import GeminiClient
from app.services.ai_capabilities import (
    NORMALIZED_REASONING_INTENSITIES,
    ReasoningIntensity,
    UnsupportedReasoningIntensityError,
    build_reasoning_config,
    get_reasoning_registry_metadata,
    load_reasoning_capabilities,
)
from app.services.ai_providers.anthropic_provider import AnthropicProvider
from app.services.ai_providers.gemini_provider import GeminiProvider


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_FILES = [
    BACKEND_ROOT / "app/services/ai_providers/base_provider.py",
    BACKEND_ROOT / "app/services/ai_providers/openai_provider.py",
    BACKEND_ROOT / "app/services/ai_providers/anthropic_provider.py",
    BACKEND_ROOT / "app/services/ai_providers/gemini_provider.py",
]


async def _collect_async_stream(stream: Any) -> list[Any]:
    return [chunk async for chunk in stream]


class _AnthropicMessagesStub:
    def __init__(self) -> None:
        self.create_kwargs: dict[str, Any] | None = None
        self.stream_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.create_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="anthropic-ok")],
            stop_reason="stop",
            usage=SimpleNamespace(input_tokens=3, output_tokens=5),
        )

    def stream(self, **kwargs: Any) -> "_AnthropicStreamStub":
        self.stream_kwargs = kwargs
        return _AnthropicStreamStub()


class _AnthropicStreamStub:
    async def __aenter__(self) -> "_AnthropicStreamStub":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False

    def __aiter__(self) -> Any:
        async def chunks() -> Any:
            yield SimpleNamespace(type="text_delta", text="anthropic-stream")
            yield SimpleNamespace(type="message_delta", stop_reason="stop")

        return chunks()


class _GeminiResponseStub:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "candidates": [{"content": {"parts": [{"text": "gemini-ok"}]}}],
            "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 4, "totalTokenCount": 6},
        }


class _GeminiStreamStub:
    async def __aenter__(self) -> "_GeminiStreamStub":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self) -> Any:
        yield "data: " + json_module.dumps({"candidates": [{"content": {"parts": [{"text": "gemini-stream"}]}}]})


class _GeminiHTTPClientStub:
    def __init__(self) -> None:
        self.post_json: dict[str, Any] | None = None
        self.stream_json: dict[str, Any] | None = None

    async def post(self, url: str, *, json: dict[str, Any]) -> _GeminiResponseStub:
        _ = url
        self.post_json = json
        return _GeminiResponseStub()

    def stream(self, method: str, url: str, *, json: dict[str, Any]) -> _GeminiStreamStub:
        _ = method
        _ = url
        self.stream_json = json
        return _GeminiStreamStub()


def test_registry_loads_required_data_contract() -> None:
    capabilities = load_reasoning_capabilities(force_reload=True)

    assert capabilities
    assert NORMALIZED_REASONING_INTENSITIES == ("auto", "off", "low", "medium", "high", "maximum")
    for capability in capabilities:
        data = capability.as_dict()
        assert {
            "provider",
            "model_pattern",
            "supported_intensities",
            "default_intensity",
            "provider_metadata",
            "last_verified_date",
            "notes",
        }.issubset(data)
        assert data["provider_metadata"]["read_only"] is True
        assert data["provider_metadata"]["native_field"]
        assert data["provider_metadata"]["payload_mappings"]
        assert data["last_verified_date"]


def test_supported_reasoning_intensity_maps_to_provider_payload() -> None:
    openai_config = build_reasoning_config(provider="openai", model="gpt-5-preview", intensity="maximum")
    assert openai_config.intensity is ReasoningIntensity.MAXIMUM
    assert openai_config.provider_payload == {"reasoning": {"effort": "high"}}

    claude_config = build_reasoning_config(provider="anthropic", model="claude-3-7-sonnet-20250219", intensity="medium")
    assert claude_config.intensity is ReasoningIntensity.MEDIUM
    assert claude_config.provider_payload == {"output_config": {"effort": "medium"}}

    gemini3_config = build_reasoning_config(provider="gemini", model="gemini-3-pro-preview", intensity="maximum")
    assert gemini3_config.intensity is ReasoningIntensity.MAXIMUM
    assert gemini3_config.provider_payload == {
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "HIGH"}}
    }

    gemini_config = build_reasoning_config(provider="gemini", model="gemini-2.5-pro", intensity="medium")
    assert gemini_config.provider_payload == {
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 4096}}
    }

    for provider, model in (
        ("openai", "gpt-5-preview"),
        ("anthropic", "claude-3-7-sonnet-20250219"),
        ("gemini", "gemini-3-pro-preview"),
        ("gemini", "gemini-2.5-pro"),
    ):
        assert build_reasoning_config(provider=provider, model=model, intensity="auto").provider_payload == {}


def test_unsupported_explicit_intensity_fails_preflight() -> None:
    # Direct registry preflight proves the rejection happens before any provider/client dispatch or network call.
    with pytest.raises(UnsupportedReasoningIntensityError, match="不支持推理强度 high"):
        build_reasoning_config(provider="openai", model="gpt-4o-mini", intensity="high")

    with pytest.raises(UnsupportedReasoningIntensityError, match="不支持推理强度 off"):
        build_reasoning_config(provider="anthropic", model="claude-3-7-sonnet-20250219", intensity="off")


def test_unknown_model_falls_back_to_auto_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    config = build_reasoning_config(provider="openai", model="custom-frontier-model", intensity="maximum")

    assert config.intensity is ReasoningIntensity.AUTO
    assert config.provider_payload == {}
    assert config.warning is not None
    assert "未知模型推理能力" in caplog.text


def test_settings_schema_exposes_normalized_reasoning_fields() -> None:
    settings = SettingsCreate(default_reasoning_intensity="high", reasoning_overrides='{"openai:gpt-5-preview":"low"}')

    assert settings.default_reasoning_intensity == "high"
    assert settings.reasoning_overrides == '{"openai:gpt-5-preview":"low"}'

    response_fields = set(SettingsResponse.model_fields)
    assert {"default_reasoning_intensity", "reasoning_overrides", "allow_ai_entity_generation"}.issubset(response_fields)
    assert "provider_native" not in response_fields

    metadata = get_reasoning_registry_metadata()
    assert metadata["intensities"] == list(NORMALIZED_REASONING_INTENSITIES)
    assert metadata["capabilities"]
    assert "provider_native" not in metadata["capabilities"][0]
    assert metadata["capabilities"][0]["provider_metadata"]["read_only"] is True


def _method_parameter_names(file_path: Path, class_name: str, method_name: str) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == method_name:
                    return [arg.arg for arg in item.args.args]
    raise AssertionError(f"{class_name}.{method_name} not found in {file_path}")


def test_provider_generate_interfaces_accept_reasoning_config() -> None:
    class_names = {
        "base_provider.py": "BaseAIProvider",
        "openai_provider.py": "OpenAIProvider",
        "anthropic_provider.py": "AnthropicProvider",
        "gemini_provider.py": "GeminiProvider",
    }

    for provider_file in PROVIDER_FILES:
        class_name = class_names[provider_file.name]
        assert "reasoning_config" in _method_parameter_names(provider_file, class_name, "generate")
        assert "reasoning_config" in _method_parameter_names(provider_file, class_name, "generate_stream")


def test_anthropic_reasoning_payload_reaches_request_kwargs_for_sync_and_stream() -> None:
    messages = _AnthropicMessagesStub()
    client = AnthropicClient.__new__(AnthropicClient)
    client.client = SimpleNamespace(messages=messages)
    provider = AnthropicProvider(client)
    reasoning_config = build_reasoning_config(
        provider="anthropic",
        model="claude-3-7-sonnet-20250219",
        intensity="medium",
    )

    response = asyncio.run(provider.generate(
        prompt="写一段摘要",
        model="claude-3-7-sonnet-20250219",
        temperature=0.4,
        max_tokens=512,
        system_prompt="保持简洁",
        reasoning_config=reasoning_config,
    ))

    assert response["content"] == "anthropic-ok"
    assert messages.create_kwargs is not None
    assert messages.create_kwargs["output_config"] == {"effort": "medium"}
    assert messages.create_kwargs["model"] == "claude-3-7-sonnet-20250219"
    assert messages.create_kwargs["temperature"] == 0.4
    assert messages.create_kwargs["max_tokens"] == 512
    assert messages.create_kwargs["system"] == "保持简洁"

    chunks = asyncio.run(_collect_async_stream(provider.generate_stream(
        prompt="继续摘要",
        model="claude-3-7-sonnet-20250219",
        temperature=0.3,
        max_tokens=256,
        reasoning_config=reasoning_config,
    )))

    assert "anthropic-stream" in chunks
    assert messages.stream_kwargs is not None
    assert messages.stream_kwargs["output_config"] == {"effort": "medium"}
    assert messages.stream_kwargs["temperature"] == 0.3
    assert messages.stream_kwargs["max_tokens"] == 256


def test_gemini_reasoning_payload_deep_merges_into_sync_and_stream_request_json() -> None:
    http_client = _GeminiHTTPClientStub()
    client = GeminiClient.__new__(GeminiClient)
    client.api_key = "test-key"
    client.base_url = "https://gemini.test/v1beta"
    client.client = http_client
    provider = GeminiProvider(client)
    reasoning_config = build_reasoning_config(
        provider="gemini",
        model="gemini-2.5-pro",
        intensity="medium",
    )

    response = asyncio.run(provider.generate(
        prompt="写一段摘要",
        model="gemini-2.5-pro",
        temperature=0.2,
        max_tokens=1024,
        system_prompt="保持简洁",
        reasoning_config=reasoning_config,
    ))

    assert response["content"] == "gemini-ok"
    assert http_client.post_json is not None
    assert http_client.post_json["generationConfig"] == {
        "temperature": 0.2,
        "maxOutputTokens": 1024,
        "thinkingConfig": {"thinkingBudget": 4096},
    }
    assert http_client.post_json["systemInstruction"] == {"parts": [{"text": "保持简洁"}]}

    chunks = asyncio.run(_collect_async_stream(provider.generate_stream(
        prompt="继续摘要",
        model="gemini-2.5-pro",
        temperature=0.1,
        max_tokens=768,
        reasoning_config=reasoning_config,
    )))

    assert chunks == ["gemini-stream"]
    assert http_client.stream_json is not None
    assert http_client.stream_json["generationConfig"] == {
        "temperature": 0.1,
        "maxOutputTokens": 768,
        "thinkingConfig": {"thinkingBudget": 4096},
    }
