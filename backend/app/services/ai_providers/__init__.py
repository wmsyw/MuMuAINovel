"""Built-in AI providers and plugin registry."""
from typing import Optional

from app.services.ai_clients.anthropic_client import AnthropicClient, cleanup_anthropic_clients
from app.services.ai_clients.base_client import cleanup_all_clients
from app.services.ai_clients.gemini_client import GeminiClient, cleanup_gemini_clients
from app.services.ai_clients.openai_client import OpenAIClient
from app.services.ai_config import AIClientConfig, default_config

from .anthropic_provider import AnthropicProvider
from .base_provider import AICapabilities, BaseAIProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider
from .registry import ProviderRegistry


def _require_api_key(api_key: Optional[str], provider: str) -> str:
    if not api_key:
        raise ValueError(f"{provider} provider requires an API key")
    return api_key


def _create_openai(
    *,
    api_key: Optional[str],
    base_url: Optional[str] = None,
    config: AIClientConfig = default_config,
) -> BaseAIProvider:
    client = OpenAIClient(_require_api_key(api_key, "openai"), base_url or "https://api.openai.com/v1", config)
    return OpenAIProvider(client)


def _create_anthropic(
    *,
    api_key: Optional[str],
    base_url: Optional[str] = None,
    config: AIClientConfig = default_config,
) -> BaseAIProvider:
    return AnthropicProvider(AnthropicClient(_require_api_key(api_key, "anthropic"), base_url, config))


def _create_gemini(
    *,
    api_key: Optional[str],
    base_url: Optional[str] = None,
    config: AIClientConfig = default_config,
) -> BaseAIProvider:
    return GeminiProvider(GeminiClient(_require_api_key(api_key, "gemini"), base_url, config))


ProviderRegistry.register("openai", _create_openai, aliases=("openai-compatible", "xiaomi-mimo"), replace=True)
ProviderRegistry.register("anthropic", _create_anthropic, aliases=("claude",), replace=True)
ProviderRegistry.register("gemini", _create_gemini, replace=True)


async def cleanup_provider_clients() -> None:
    """Close process-wide built-in client pools during application shutdown."""
    await cleanup_all_clients()
    await cleanup_anthropic_clients()
    await cleanup_gemini_clients()


__all__ = [
    "AICapabilities",
    "AnthropicProvider",
    "BaseAIProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "ProviderRegistry",
    "cleanup_provider_clients",
]