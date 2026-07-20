"""Dynamic registry for AI provider factories."""
from collections.abc import Callable
from typing import ClassVar

from .base_provider import BaseAIProvider

ProviderFactory = Callable[..., BaseAIProvider]


class ProviderRegistry:
    """Process-wide registry for pluggable AI provider factories."""

    _providers: ClassVar[dict[str, ProviderFactory]] = {}
    _aliases: ClassVar[dict[str, str]] = {}

    @staticmethod
    def _normalize(name: str) -> str:
        normalized = str(name or "").strip().lower().replace("_", "-")
        if not normalized:
            raise ValueError("Provider name cannot be empty")
        return normalized

    @classmethod
    def register(
        cls,
        name: str,
        factory: ProviderFactory,
        *,
        aliases: tuple[str, ...] = (),
        replace: bool = False,
    ) -> None:
        key = cls._normalize(name)
        if key in cls._aliases:
            raise ValueError(f"Provider name conflicts with alias: {key}")
        if key in cls._providers and not replace:
            raise ValueError(f"Provider already registered: {key}")

        normalized_aliases = tuple(cls._normalize(alias) for alias in aliases)
        if key in normalized_aliases:
            raise ValueError(f"Provider alias conflicts with provider: {key}")
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise ValueError(f"Provider aliases must be unique: {key}")

        for alias_key in normalized_aliases:
            if alias_key in cls._providers:
                raise ValueError(f"Provider alias conflicts with provider: {alias_key}")
            existing = cls._aliases.get(alias_key)
            if existing and existing != key and not replace:
                raise ValueError(f"Provider alias already registered: {alias_key}")

        if replace:
            cls._aliases = {
                alias: target
                for alias, target in cls._aliases.items()
                if target != key and alias not in normalized_aliases
            }
        cls._providers[key] = factory
        for alias_key in normalized_aliases:
            cls._aliases[alias_key] = key

    @classmethod
    def unregister(cls, name: str) -> None:
        key = cls.resolve(name)
        _ = cls._providers.pop(key, None)
        cls._aliases = {
            alias: target
            for alias, target in cls._aliases.items()
            if cls.resolve(target) != key
        }

    @classmethod
    def resolve(cls, name: str) -> str:
        key = cls._normalize(name)
        visited: set[str] = set()
        while key in cls._aliases:
            if key in visited:
                raise ValueError(f"Provider alias cycle detected: {name}")
            visited.add(key)
            key = cls._aliases[key]
        return key

    @classmethod
    def get(cls, name: str, **config: object) -> BaseAIProvider:
        key = cls.resolve(name)
        factory = cls._providers.get(key)
        if factory is None:
            available = ", ".join(cls.available()) or "none"
            raise ValueError(f"Unknown provider: {name}. Available providers: {available}")
        provider = factory(**config)
        return provider

    @classmethod
    def available(cls) -> tuple[str, ...]:
        return tuple(sorted(cls._providers))
