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
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

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


def test_ai_service_normalizes_aliases_and_passes_reasoning_contract_to_provider() -> None:
    provider = _CapturingProvider()
    service = AIService(
        api_provider="mumu",
        api_key="",
        api_base_url="https://api.example.invalid/v1",
        default_model="gpt-5-preview",
        default_temperature=0.3,
        default_max_tokens=128,
        default_system_prompt="系统提示",
        enable_mcp=False,
    )
    service.__dict__["_openai_provider"] = provider

    result = asyncio.run(
        service.generate_text(
            prompt="写一段摘要",
            provider="mumu",
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
