import asyncio

from app.services.ai_token_limits import (
    OPENAI_COMPATIBLE_MAX_TOKENS,
    prime_models_dev_catalog,
    resolve_openai_compatible_max_tokens,
)


def test_models_dev_limit_matches_router_prefixed_model_id() -> None:
    prime_models_dev_catalog(
        {
            "llmgateway": {
                "models": {
                    "deepseek-v4-flash": {
                        "id": "deepseek-v4-flash",
                        "limit": {"context": 1_000_000, "output": 384_000},
                    }
                }
            }
        }
    )

    resolution = asyncio.run(
        resolve_openai_compatible_max_tokens(
            model="custom-router/deepseek-v4-flash",
            max_tokens=1_000_000,
        )
    )

    assert resolution.normalized == 384_000
    assert resolution.limit == 384_000
    assert resolution.source == "models.dev"
    assert resolution.matched_provider == "llmgateway"
    assert resolution.matched_model == "deepseek-v4-flash"


def test_models_dev_limit_falls_back_when_model_is_unknown() -> None:
    prime_models_dev_catalog({})

    resolution = asyncio.run(
        resolve_openai_compatible_max_tokens(
            model="unknown-router/unknown-model",
            max_tokens=1_000_000,
        )
    )

    assert resolution.normalized == OPENAI_COMPATIBLE_MAX_TOKENS
    assert resolution.limit == OPENAI_COMPATIBLE_MAX_TOKENS
    assert resolution.source == "fallback"
