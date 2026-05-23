from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false

import sys
import types

import pytest
from httpx import AsyncClient


if "mcp" not in sys.modules:
    _mcp_stub = types.ModuleType("mcp")
    setattr(_mcp_stub, "ClientSession", type("ClientSession", (), {}))
    setattr(_mcp_stub, "types", types.SimpleNamespace(TextContent=type("TextContent", (), {}), ImageContent=type("ImageContent", (), {})))
    _client_stub = types.ModuleType("mcp.client")
    _streamable_stub = types.ModuleType("mcp.client.streamable_http")
    _sse_stub = types.ModuleType("mcp.client.sse")

    class _StubContext:
        async def __aenter__(self) -> tuple[None, None, None]:
            return (None, None, None)

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
            return False

    def _streamablehttp_client(**kwargs: object) -> _StubContext:
        _ = kwargs
        return _StubContext()

    def _sse_client(**kwargs: object) -> _StubContext:
        _ = kwargs
        return _StubContext()

    setattr(_streamable_stub, "streamablehttp_client", _streamablehttp_client)
    setattr(_sse_stub, "sse_client", _sse_client)
    _ = sys.modules.setdefault("mcp", _mcp_stub)
    _ = sys.modules.setdefault("mcp.client", _client_stub)
    _ = sys.modules.setdefault("mcp.client.streamable_http", _streamable_stub)
    _ = sys.modules.setdefault("mcp.client.sse", _sse_stub)

_memory_service_stub = types.ModuleType("app.services.memory_service")
setattr(_memory_service_stub, "memory_service", types.SimpleNamespace())
_ = sys.modules.setdefault("app.services.memory_service", _memory_service_stub)


class _StubEmailService:
    async def send_mail(self, **_: object) -> None:
        return None


_email_service_stub = types.ModuleType("app.services.email_service")
setattr(_email_service_stub, "email_service", _StubEmailService())
_ = sys.modules.setdefault("app.services.email_service", _email_service_stub)


pytestmark = pytest.mark.anyio


def _trace_payload() -> dict:
    return {
        "trace_version": 1,
        "layers": [
            {
                "id": "workshop-item",
                "source_type": "workshop_item",
                "label": "工坊导入写作风格",
                "content": "使用细腻、压迫的雨夜氛围。",
                "order": 40,
                "metadata": {"workshop_item_id": "wk-001"},
            },
            {
                "id": "system-template",
                "source_type": "system_template",
                "label": "章节系统模板",
                "content": "你是专注长篇连载的小说作者。",
                "order": 10,
                "metadata": {"template_key": "CHAPTER_GENERATION_ONE_TO_MANY"},
            },
        ],
    }


async def test_preset_boundary_does_not_duplicate_workshop_stack(test_client: AsyncClient) -> None:
    first = await test_client.post("/api/prompt-workshop/preset-boundary/assembly-trace", json=_trace_payload())
    second = await test_client.post("/api/prompt-workshop/preset-boundary/assembly-trace", json=_trace_payload())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["success"] is True
    assert body["boundary"] == {
        "mode": "trace_only",
        "owner": "prompt_workshop",
        "duplicates_prompt_stack": False,
        "persistence": "none",
        "reason": "Prompt Workshop 已覆盖提示词浏览、导入、提交、审核和本地写作风格导入；此处仅补齐确定性组装追踪。",
    }
    trace = body["trace"]
    assert trace["trace_version"] == 1
    assert trace["schema_version"] == "prompt-assembly-trace/v1"
    assert trace["preset_boundary"] == "prompt_workshop"
    assert trace["validation"]["valid"] is True
    assert trace["layer_order"] == ["system-template", "workshop-item"]
    assert trace["final_prompt"] == "你是专注长篇连载的小说作者。\n\n使用细腻、压迫的雨夜氛围。"


async def test_invalid_preset_layer_returns_validation_error(test_client: AsyncClient) -> None:
    response = await test_client.post(
        "/api/prompt-workshop/preset-boundary/assembly-trace",
        json={
            "trace_version": 1,
            "layers": [
                {"id": "bad", "source_type": "script", "content": "hidden mutable state"},
            ],
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["valid"] is False
    assert detail["expected_trace_version"] == 1
    assert detail["errors"][0]["message"] == "禁止的提示词层来源: script"
