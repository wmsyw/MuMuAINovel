import asyncio
import ast
import json
from pathlib import Path
from typing import Any, Dict

from app.services.ai_capabilities import build_reasoning_config
from app.services.ai_clients.openai_client import OpenAIClient
from app.services.ai_providers.openai_provider import OpenAIProvider


class CapturingOpenAIClient(OpenAIClient):
    def __init__(self, response: Dict[str, Any] | None = None):
        super().__init__("test-key", "https://api.openai.test/v1")
        self.response = response or {}
        self.calls: list[Dict[str, Any]] = []

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any],
        stream: bool = False,
    ) -> Any:
        self.calls.append({"method": method, "endpoint": endpoint, "payload": payload, "stream": stream})
        return self.response


class FakeStreamResponse:
    def __init__(self, events: list[Dict[str, Any]]):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for event in self.events:
            yield f"data: {json.dumps(event)}"


class StreamingOpenAIClient(CapturingOpenAIClient):
    def __init__(self, events: list[Dict[str, Any]]):
        super().__init__()
        self.events = events

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any],
        stream: bool = False,
    ) -> Any:
        self.calls.append({"method": method, "endpoint": endpoint, "payload": payload, "stream": stream})
        assert stream is True
        return FakeStreamResponse(self.events)


def collect_async(async_iterable):
    async def _collect():
        return [item async for item in async_iterable]

    return asyncio.run(_collect())


def test_create_response_uses_responses_endpoint_and_normalizes_output() -> None:
    client = CapturingOpenAIClient(
        {
            "id": "resp_123",
            "object": "response",
            "model": "gpt-5-preview",
            "status": "completed",
            "previous_response_id": "resp_122",
            "reasoning": {"summary": [{"text": "non-canonical note"}]},
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "你好"}]},
                {"type": "function_call", "call_id": "call_lookup", "name": "lookup", "arguments": '{"q":"月亮"}'},
            ],
            "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
        }
    )

    result = asyncio.run(
        client.create_response(
            messages=[{"role": "system", "content": "系统"}, {"role": "user", "content": "问题"}],
            model="gpt-5-preview",
            temperature=0.2,
            max_tokens=512,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup",
                        "parameters": {"type": "object", "$schema": "http://json-schema.org/draft-07/schema#"},
                    },
                }
            ],
            tool_choice="auto",
            reasoning_payload={"reasoning": {"effort": "high"}},
        )
    )

    assert client.calls[0]["endpoint"] == "/responses"
    payload = client.calls[0]["payload"]
    assert payload["input"] == [
        {"role": "system", "content": [{"type": "input_text", "text": "系统"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "问题"}]},
    ]
    assert payload["max_output_tokens"] == 512
    assert payload["reasoning"] == {"effort": "high"}
    assert payload["tools"] == [
        {"type": "function", "name": "lookup", "description": "Lookup", "parameters": {"type": "object"}}
    ]
    assert result["content"] == "你好"
    assert result["tool_calls"] == [
        {"id": "call_lookup", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"月亮"}'}}
    ]
    assert result["finish_reason"] == "tool_calls"
    assert result["usage"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert result["provider_metadata"]["response_id"] == "resp_123"
    assert result["reasoning_continuation"]["previous_response_id"] == "resp_122"


def test_create_response_stream_normalizes_text_tool_usage_and_done_events() -> None:
    client = StreamingOpenAIClient(
        [
            {"type": "response.output_text.delta", "delta": "你"},
            {"type": "response.output_text.delta", "delta": "好"},
            {
                "type": "response.output_item.added",
                "output_index": 1,
                "item": {"id": "fc_1", "call_id": "call_lookup", "type": "function_call", "name": "lookup"},
            },
            {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '{"q":'},
            {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '"月亮"}'},
            {
                "type": "response.output_item.done",
                "output_index": 1,
                "item": {
                    "id": "fc_1",
                    "call_id": "call_lookup",
                    "type": "function_call",
                    "name": "lookup",
                    "arguments": '{"q":"月亮"}',
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_456",
                    "status": "completed",
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                },
            },
        ]
    )

    chunks = collect_async(
        client.create_response_stream(
            messages=[{"role": "user", "content": "问题"}],
            model="gpt-5-preview",
            temperature=0.1,
            max_tokens=128,
            reasoning_payload={"reasoning": {"effort": "medium"}},
        )
    )

    assert client.calls[0]["endpoint"] == "/responses"
    assert client.calls[0]["payload"]["stream"] is True
    assert chunks[0] == {"content": "你"}
    assert chunks[1] == {"content": "好"}
    assert chunks[2] == {
        "tool_calls": [
            {"id": "call_lookup", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"月亮"}'}}
        ]
    }
    assert chunks[3] == {"usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}
    assert chunks[4]["provider_metadata"]["response_id"] == "resp_456"
    assert chunks[5] == {"done": True, "finish_reason": "stop"}


def test_openai_provider_routes_reasoning_path_to_responses_and_legacy_to_chat() -> None:
    responses_client = CapturingOpenAIClient(
        {"id": "resp_1", "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "响应"}]}]}
    )
    provider = OpenAIProvider(responses_client)

    response = asyncio.run(
        provider.generate(
            prompt="问题",
            model="gpt-5-preview",
            temperature=0.4,
            max_tokens=256,
            reasoning_config=build_reasoning_config(provider="openai", model="gpt-5-preview", intensity="high"),
        )
    )

    assert response["content"] == "响应"
    assert responses_client.calls[0]["endpoint"] == "/responses"
    assert responses_client.calls[0]["payload"]["reasoning"] == {"effort": "high"}

    chat_client = CapturingOpenAIClient(
        {"choices": [{"message": {"content": "聊天"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1}}
    )
    provider = OpenAIProvider(chat_client)
    response = asyncio.run(
        provider.generate(
            prompt="问题",
            model="gpt-4o-mini",
            temperature=0.4,
            max_tokens=256,
            reasoning_config=build_reasoning_config(provider="openai", model="gpt-4o-mini", intensity="auto"),
        )
    )

    assert response["content"] == "聊天"
    assert chat_client.calls[0]["endpoint"] == "/chat/completions"
    assert "input" not in chat_client.calls[0]["payload"]


def test_no_separate_openai_responses_client_class_exists() -> None:
    client_file = Path(__file__).resolve().parents[1] / "app/services/ai_clients/openai_client.py"
    tree = ast.parse(client_file.read_text(encoding="utf-8"))

    class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert "OpenAIClient" in class_names
    assert "OpenAIResponsesClient" not in class_names
