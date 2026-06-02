import asyncio
from typing import Any, Dict

from app.services import ai_token_limits
from app.services.ai_clients.openai_client import OpenAIClient
from app.services.ai_providers.openai_provider import OpenAIProvider
from app.services.ai_service import AIService


class CapturingOpenAIClient(OpenAIClient):
    def __init__(self, chat_response: Dict[str, Any] | None = None, responses_response: Dict[str, Any] | None = None):
        super().__init__("test-key", "https://api.openai.test/v1")
        self.chat_response = chat_response or {
            "choices": [{"message": {"content": "legacy ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }
        self.responses_response = responses_response or {
            "id": "resp_service",
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "responses ok"}]}],
            "usage": {"input_tokens": 4, "output_tokens": 6, "total_tokens": 10},
        }
        self.calls: list[Dict[str, Any]] = []

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any],
        stream: bool = False,
    ) -> Any:
        self.calls.append({"method": method, "endpoint": endpoint, "payload": payload, "stream": stream})
        if endpoint == "/responses":
            return self.responses_response
        return self.chat_response


def seed_models_dev_limit(*, model: str, output: int) -> None:
    ai_token_limits.prime_models_dev_catalog(
        {"llmgateway": {"models": {model: {"id": model, "limit": {"context": 1_000_000, "output": output}}}}},
    )


def make_service(
    client: CapturingOpenAIClient,
    default_model: str,
    default_reasoning_intensity: str = "auto",
    default_max_tokens: int = 256,
) -> AIService:
    service = AIService(
        api_provider="mumu",
        api_key="test-key",
        api_base_url="https://api.openai.test/v1",
        default_model=default_model,
        default_temperature=0.3,
        default_max_tokens=default_max_tokens,
        default_system_prompt="系统提示",
        default_reasoning_intensity=default_reasoning_intensity,
        enable_mcp=False,
    )
    service._openai_provider = OpenAIProvider(client)
    return service


def test_ai_service_preserves_mumu_alias_and_legacy_chat_completion_shape() -> None:
    client = CapturingOpenAIClient()
    service = make_service(client, default_model="gpt-4o-mini")

    result = asyncio.run(
        service.generate_text(
            prompt="写一段话",
            provider="mumu",
            model="gpt-4o-mini",
            auto_mcp=False,
            handle_tool_calls=False,
        )
    )

    assert service.api_provider == "openai"
    assert result["content"] == "legacy ok"
    assert result["usage"] == {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    assert client.calls == [
        {
            "method": "POST",
            "endpoint": "/chat/completions",
            "stream": False,
            "payload": {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "系统提示"},
                    {"role": "user", "content": "写一段话"},
                ],
                "temperature": 0.3,
                "max_tokens": 256,
            },
        }
    ]


def test_ai_service_routes_openai_reasoning_request_through_responses_without_public_api_change() -> None:
    client = CapturingOpenAIClient()
    service = make_service(client, default_model="gpt-5-preview")

    result = asyncio.run(
        service.generate_text(
            prompt="推理回答",
            provider="openai",
            model="gpt-5-preview",
            reasoning_intensity="high",
            auto_mcp=False,
            handle_tool_calls=False,
        )
    )

    assert result["content"] == "responses ok"
    assert client.calls[0]["endpoint"] == "/responses"
    assert client.calls[0]["payload"]["input"] == [
        {"role": "system", "content": [{"type": "input_text", "text": "系统提示"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "推理回答"}]},
    ]
    assert client.calls[0]["payload"]["reasoning"] == {"effort": "high"}
    assert "messages" not in client.calls[0]["payload"]


def test_ai_service_explicit_auto_suppresses_default_deepseek_reasoning_payload() -> None:
    client = CapturingOpenAIClient()
    service = make_service(
        client,
        default_model="deepseek-v4-flash",
        default_reasoning_intensity="high",
    )

    result = asyncio.run(
        service.generate_text(
            prompt="生成JSON",
            provider="openai",
            model="deepseek-v4-flash",
            reasoning_intensity="auto",
            auto_mcp=False,
            handle_tool_calls=False,
        )
    )

    assert result["content"] == "legacy ok"
    assert client.calls[0]["endpoint"] == "/chat/completions"
    payload = client.calls[0]["payload"]
    assert payload["model"] == "deepseek-v4-flash"
    assert "thinking" not in payload
    assert "reasoning_effort" not in payload


def test_ai_service_clamps_oversized_user_default_max_tokens_for_openai_compat() -> None:
    seed_models_dev_limit(model="deepseek-v4-flash", output=384_000)
    client = CapturingOpenAIClient()
    service = make_service(
        client,
        default_model="deepseek-v4-flash",
        default_max_tokens=1_000_000,
    )

    result = asyncio.run(
        service.generate_text(
            prompt="生成JSON",
            provider="openai",
            model="deepseek-v4-flash",
            auto_mcp=False,
            handle_tool_calls=False,
        )
    )

    assert result["content"] == "legacy ok"
    assert client.calls[0]["payload"]["max_tokens"] == 384_000
