from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportImplicitOverride=false, reportPrivateUsage=false, reportUnusedCallResult=false

import ast
import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest

from app.services.ai_capabilities import UnsupportedReasoningIntensityError, build_reasoning_config
from app.services.ai_providers.base_provider import BaseAIProvider
from app.services.ai_providers.registry import ProviderRegistry
from app.services.ai_service import AIService


BACKEND_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = BACKEND_ROOT / "app" / "api"
PROVIDER_SDK_NAMES = {
    "OpenAIClient",
    "AnthropicClient",
    "GeminiClient",
    "AsyncOpenAI",
    "AsyncAnthropic",
    "ClientSession",
}


class _CapturingProvider(BaseAIProvider):
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self.close_calls = 0
        self.response = response

    async def close(self) -> None:
        self.close_calls += 1

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        reasoning_config: Any = None,
    ) -> dict[str, Any]:
        self.generate_calls.append(
            {
                "prompt": prompt,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "system_prompt": system_prompt,
                "tools": tools,
                "tool_choice": tool_choice,
                "reasoning_config": reasoning_config,
            }
        )
        if self.response is not None:
            return self.response
        return {
            "content": "provider-ok",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        user_id: str | None = None,
        reasoning_config: Any = None,
        mcp_max_rounds: int = 3,
        allowed_tool_names: set[str] | None = None,
        db_session: Any = None,
    ) -> AsyncGenerator[str | dict[str, Any], None]:
        self.stream_calls.append(
            {
                "prompt": prompt,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "system_prompt": system_prompt,
                "tools": tools,
                "tool_choice": tool_choice,
                "user_id": user_id,
                "reasoning_config": reasoning_config,
                "mcp_max_rounds": mcp_max_rounds,
                "allowed_tool_names": allowed_tool_names,
                "db_session": db_session,
            }
        )
        async for chunk in self._empty_stream():
            yield chunk

    async def _empty_stream(self) -> AsyncGenerator[str | dict[str, Any], None]:
        for chunk in ():
            yield chunk


def _api_python_files() -> list[Path]:
    return sorted(API_ROOT.rglob("*.py"))


def _iter_direct_calls(tree: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _imported_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.ImportFrom):
            module = item.module or ""
            if module.startswith("app.services.ai_clients") or module.startswith("app.services.ai_providers"):
                names.update(alias.name for alias in item.names)
        if isinstance(item, ast.Import):
            for alias in item.names:
                if alias.name.startswith("app.services.ai_clients") or alias.name.startswith("app.services.ai_providers"):
                    names.add(alias.name)
    return names


def _direct_sdk_constructor_hits(file_path: Path) -> list[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    hits: list[str] = []

    for call in _iter_direct_calls(tree):
        func = call.func
        if isinstance(func, ast.Name) and func.id in PROVIDER_SDK_NAMES:
            hits.append(func.id)
        elif isinstance(func, ast.Attribute) and func.attr in PROVIDER_SDK_NAMES:
            hits.append(func.attr)

    return hits


def test_unsupported_capability_is_handled() -> None:
    service = AIService(
        api_provider="openai",
        api_key="",
        api_base_url="https://api.example.invalid/v1",
        default_model="gpt-4o-mini",
        default_temperature=0.2,
        default_max_tokens=64,
        default_system_prompt="系统提示",
        enable_mcp=False,
    )

    with pytest.raises(UnsupportedReasoningIntensityError, match="不支持推理强度"):
        _ = asyncio.run(
            service.generate_text(
                prompt="写一段话",
                provider="openai",
                model="gpt-4o-mini",
                reasoning_intensity="high",
                auto_mcp=False,
                handle_tool_calls=False,
            )
        )


def test_ai_service_passes_reasoning_contract_to_registered_provider() -> None:
    provider = _CapturingProvider()
    service = AIService(
        api_provider="openai",
        api_key="",
        api_base_url="https://api.example.invalid/v1",
        default_model="gpt-5-preview",
        default_temperature=0.3,
        default_max_tokens=128,
        default_system_prompt="系统提示",
        enable_mcp=False,
    )
    service._providers["openai"] = provider

    result = asyncio.run(
        service.generate_text(
            prompt="写一段摘要",
            provider="openai",
            model="gpt-5-preview",
            temperature=0.4,
            max_tokens=256,
            auto_mcp=False,
            handle_tool_calls=False,
            reasoning_intensity="high",
        )
    )

    assert service.api_provider == "openai"
    assert result["content"] == "provider-ok"
    assert len(provider.generate_calls) == 1
    call = provider.generate_calls[0]
    assert call["prompt"] == "写一段摘要"
    assert call["model"] == "gpt-5-preview"
    assert call["temperature"] == 0.4
    assert call["max_tokens"] == 256
    assert call["system_prompt"] == "系统提示"
    assert call["reasoning_config"] is not None
    assert call["reasoning_config"].provider == "openai"
    assert call["reasoning_config"].intensity.value == "high"
    assert call["reasoning_config"].provider_payload == {"reasoning": {"effort": "high"}}


def test_router_source_does_not_directly_instantiate_provider_sdk_clients() -> None:
    sdk_hits: dict[str, list[str]] = {}

    for file_path in _api_python_files():
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        imported = _imported_names(tree)
        direct_hits = _direct_sdk_constructor_hits(file_path)
        if imported or direct_hits:
            sdk_hits[str(file_path.relative_to(BACKEND_ROOT))] = sorted(imported.union(direct_hits))

    assert sdk_hits == {}


def test_reasoning_registry_unknown_model_returns_auto_without_provider_payload() -> None:
    config = build_reasoning_config(provider="openai", model="custom-frontier-model", intensity="maximum")

    assert config.intensity.value == "auto"
    assert config.provider_payload == {}
    assert config.warning is not None


def test_selected_alias_uses_canonical_storage_and_keyless_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    canonical_name = "contract-local-provider"
    factory_calls: list[dict[str, Any]] = []

    def factory(**config: object) -> BaseAIProvider:
        factory_calls.append(config)
        assert config["api_key"] is None
        return _CapturingProvider()

    registry_get_calls: list[str] = []
    original_get = ProviderRegistry.get

    def recording_get(name: str, **config: object) -> BaseAIProvider:
        registry_get_calls.append(ProviderRegistry.resolve(name))
        return original_get(name, **config)

    monkeypatch.setattr(ProviderRegistry, "get", recording_get)
    ProviderRegistry.register(canonical_name, factory, aliases=("Contract_Local",), replace=True)
    try:
        service = AIService(
            api_provider="CONTRACT_LOCAL",
            api_key=None,
            api_base_url=None,
            default_model="local-model",
            default_temperature=0.2,
            default_max_tokens=64,
            enable_mcp=False,
        )

        assert service.api_provider == canonical_name
        assert tuple(service._providers) == (canonical_name,)
        assert registry_get_calls == [canonical_name]
        assert len(factory_calls) == 1
    finally:
        ProviderRegistry.unregister(canonical_name)


def test_ai_service_close_is_scoped_to_owned_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    service_a = AIService(api_provider="openai", api_key="", enable_mcp=False)
    service_b = AIService(api_provider="openai", api_key="", enable_mcp=False)
    provider_a = _CapturingProvider()
    provider_b = _CapturingProvider()
    service_a._providers["openai"] = provider_a
    service_b._providers["openai"] = provider_b

    async def unexpected_global_cleanup() -> None:
        raise AssertionError("service close must not perform process-wide cleanup")

    monkeypatch.setattr("app.services.ai_service.cleanup_provider_clients", unexpected_global_cleanup)

    asyncio.run(service_a.close())
    asyncio.run(service_a.close())

    assert provider_a.close_calls == 1
    assert provider_b.close_calls == 0


def test_null_tool_only_content_is_normalized_to_empty_text() -> None:
    base_provider = _CapturingProvider(response={"content": None})
    assert asyncio.run(
        base_provider.generate_text(
            prompt="prompt",
            model="model",
            temperature=0.2,
            max_tokens=64,
        )
    ) == ""

    tool_only_provider = _CapturingProvider(
        response={
            "content": None,
            "tool_calls": [{"function": {"name": "lookup"}}],
            "finish_reason": "tool_calls",
        }
    )
    service = AIService(api_provider="openai", api_key="", enable_mcp=False)
    service._providers["openai"] = tool_only_provider

    result = asyncio.run(
        service.generate_text(
            prompt="prompt",
            auto_mcp=False,
            handle_tool_calls=False,
        )
    )

    assert result["content"] == ""
