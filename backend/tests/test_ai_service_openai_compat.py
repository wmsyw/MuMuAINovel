import asyncio
from typing import Any, Dict

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


def make_service(client: CapturingOpenAIClient, default_model: str) -> AIService:
    service = AIService(
        api_provider="mumu",
        api_key="test-key",
        api_base_url="https://api.openai.test/v1",
        default_model=default_model,
        default_temperature=0.3,
        default_max_tokens=256,
        default_system_prompt="系统提示",
        default_reasoning_intensity="auto",
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
