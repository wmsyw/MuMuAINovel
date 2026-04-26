import ast
from pathlib import Path

import pytest

from app.schemas.settings import SettingsCreate, SettingsResponse
from app.services.ai_capabilities import (
    NORMALIZED_REASONING_INTENSITIES,
    ReasoningIntensity,
    UnsupportedReasoningIntensityError,
    build_reasoning_config,
    get_reasoning_registry_metadata,
    load_reasoning_capabilities,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_FILES = [
    BACKEND_ROOT / "app/services/ai_providers/base_provider.py",
    BACKEND_ROOT / "app/services/ai_providers/openai_provider.py",
    BACKEND_ROOT / "app/services/ai_providers/anthropic_provider.py",
    BACKEND_ROOT / "app/services/ai_providers/gemini_provider.py",
]


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
            "provider_native",
            "provider_payload_mappings",
            "last_verified_date",
            "notes",
        }.issubset(data)
        assert data["provider_payload_mappings"]
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

    metadata = get_reasoning_registry_metadata()
    assert metadata["intensities"] == list(NORMALIZED_REASONING_INTENSITIES)
    assert metadata["capabilities"]


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
