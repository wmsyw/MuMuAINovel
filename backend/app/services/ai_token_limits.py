import time
from dataclasses import dataclass
from typing import cast

import httpx

from app.logger import get_logger


logger = get_logger(__name__)

MODELS_DEV_API_URL = "https://models.dev/api.json"
MODELS_DEV_CACHE_TTL_SECONDS = 24 * 60 * 60
MODELS_DEV_FETCH_TIMEOUT_SECONDS = 10.0
OPENAI_COMPATIBLE_FALLBACK_MAX_TOKENS = 393_216
OPENAI_COMPATIBLE_MAX_TOKENS = OPENAI_COMPATIBLE_FALLBACK_MAX_TOKENS
OPENAI_COMPATIBLE_MIN_TOKENS = 1


@dataclass(frozen=True)
class TokenLimitResolution:
    normalized: int
    limit: int
    source: str
    matched_provider: str | None = None
    matched_model: str | None = None


@dataclass
class _ModelsDevCache:
    data: dict[str, object] | None = None
    expires_at: float = 0.0


_models_dev_cache = _ModelsDevCache()


def _normalize_model_key(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _model_candidates(model: str) -> list[str]:
    normalized = _normalize_model_key(model)
    candidates = [normalized]
    for separator in ("/", ":"):
        if separator in normalized:
            candidates.append(normalized.rsplit(separator, 1)[-1])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _output_limit(model_info: object) -> int | None:
    if not isinstance(model_info, dict):
        return None
    model_data = cast(dict[str, object], model_info)
    limit_obj = model_data.get("limit")
    if not isinstance(limit_obj, dict):
        return None
    limit = cast(dict[str, object], limit_obj)
    output = limit.get("output")
    if isinstance(output, int) and output >= OPENAI_COMPATIBLE_MIN_TOKENS:
        return output
    return None


async def _fetch_models_dev_catalog() -> dict[str, object] | None:
    try:
        async with httpx.AsyncClient(timeout=MODELS_DEV_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                MODELS_DEV_API_URL,
                headers={"User-Agent": "MuMuAINovel/1.0 (+https://models.dev)"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("models.dev 模型参数获取失败，将使用兼容兜底上限: %s", exc)
        return None
    if not isinstance(data, dict):
        logger.warning("models.dev 模型参数响应不是对象，将使用兼容兜底上限")
        return None
    return cast(dict[str, object], data)


async def _get_models_dev_catalog() -> dict[str, object] | None:
    now = time.monotonic()
    if _models_dev_cache.data is not None and _models_dev_cache.expires_at > now:
        return _models_dev_cache.data

    data = await _fetch_models_dev_catalog()
    if data is not None:
        _models_dev_cache.data = data
        _models_dev_cache.expires_at = now + MODELS_DEV_CACHE_TTL_SECONDS
    return _models_dev_cache.data


def _find_output_limit_in_catalog(
    catalog: dict[str, object],
    model: str,
    preferred_provider: str | None = None,
) -> tuple[int, str, str] | None:
    candidates = _model_candidates(model)
    provider_ids = list(catalog.keys())
    if preferred_provider:
        normalized_provider = _normalize_model_key(preferred_provider)
        provider_ids.sort(key=lambda provider_id: 0 if _normalize_model_key(provider_id) == normalized_provider else 1)

    for provider_id in provider_ids:
        provider_obj = catalog.get(provider_id)
        if not isinstance(provider_obj, dict):
            continue
        provider = cast(dict[str, object], provider_obj)
        models_obj = provider.get("models")
        if not isinstance(models_obj, dict):
            continue
        models = cast(dict[str, object], models_obj)
        for candidate in candidates:
            for model_id, model_info in models.items():
                if not isinstance(model_info, dict):
                    continue
                model_data = cast(dict[str, object], model_info)
                model_keys = [
                    _normalize_model_key(str(model_id)),
                    _normalize_model_key(str(model_data.get("id", ""))),
                ]
                if candidate not in model_keys:
                    continue
                limit = _output_limit(model_data)
                if limit is not None:
                    return limit, provider_id, str(model_id)

    for provider_id in provider_ids:
        provider_obj = catalog.get(provider_id)
        if not isinstance(provider_obj, dict):
            continue
        provider = cast(dict[str, object], provider_obj)
        models_obj = provider.get("models")
        if not isinstance(models_obj, dict):
            continue
        models = cast(dict[str, object], models_obj)
        for model_id, model_info in models.items():
            if not isinstance(model_info, dict):
                continue
            model_key = _normalize_model_key(str(model_id))
            model_data = cast(dict[str, object], model_info)
            info_id = _normalize_model_key(str(model_data.get("id", "")))
            if not any(model_key.endswith(f"/{candidate}") or info_id.endswith(f"/{candidate}") for candidate in candidates):
                continue
            limit = _output_limit(model_data)
            if limit is not None:
                return limit, provider_id, str(model_id)
    return None


def prime_models_dev_catalog(catalog: dict[str, object], ttl_seconds: int = MODELS_DEV_CACHE_TTL_SECONDS) -> None:
    _models_dev_cache.data = catalog
    _models_dev_cache.expires_at = time.monotonic() + ttl_seconds


def clamp_openai_compatible_max_tokens(max_tokens: int) -> int:
    return max(OPENAI_COMPATIBLE_MIN_TOKENS, min(max_tokens, OPENAI_COMPATIBLE_MAX_TOKENS))


async def resolve_openai_compatible_max_tokens(
    *,
    model: str,
    max_tokens: int,
    preferred_provider: str | None = None,
) -> TokenLimitResolution:
    if max_tokens < OPENAI_COMPATIBLE_MIN_TOKENS:
        return TokenLimitResolution(
            normalized=OPENAI_COMPATIBLE_MIN_TOKENS,
            limit=OPENAI_COMPATIBLE_MIN_TOKENS,
            source="minimum",
        )

    if max_tokens <= OPENAI_COMPATIBLE_FALLBACK_MAX_TOKENS and _models_dev_cache.data is None:
        return TokenLimitResolution(
            normalized=max_tokens,
            limit=OPENAI_COMPATIBLE_FALLBACK_MAX_TOKENS,
            source="not_required",
        )

    catalog = await _get_models_dev_catalog()
    if catalog:
        match = _find_output_limit_in_catalog(catalog, model, preferred_provider)
        if match:
            limit, provider_id, model_id = match
            return TokenLimitResolution(
                normalized=min(max_tokens, limit),
                limit=limit,
                source="models.dev",
                matched_provider=provider_id,
                matched_model=model_id,
            )

    normalized = clamp_openai_compatible_max_tokens(max_tokens)
    return TokenLimitResolution(
        normalized=normalized,
        limit=OPENAI_COMPATIBLE_FALLBACK_MAX_TOKENS,
        source="fallback",
    )
