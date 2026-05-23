from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportPrivateUsage=false, reportMissingParameterType=false, reportUnknownLambdaType=false, reportUnusedCallResult=false

import ast
import asyncio
import json
import sys
import types
from pathlib import Path
from typing import Any

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

from app.mcp.facade import mcp_client
from app.schemas.mcp_plugin import MCPToolCall


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MCP_PLUGINS_FILE = BACKEND_ROOT / "app" / "api" / "mcp_plugins.py"


def test_tool_contract_stability() -> None:
    tools = [
        {
            "name": "lookup_entry",
            "description": "查找条目",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        }
    ]

    formatted = mcp_client.format_tools_for_openai(tools, "lorebook")
    assert formatted == [
        {
            "type": "function",
            "function": {
                "name": "lorebook_lookup_entry",
                "description": "查找条目",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }
    ]

    assert mcp_client.parse_function_name("lorebook_lookup_entry") == ("lorebook", "lookup_entry")
    assert mcp_client.parse_function_name("lorebook.lookup") == ("lorebook", "lookup")

    tool_call = MCPToolCall(plugin_id="plugin-1", tool_name="lookup_entry")
    assert tool_call.arguments == {}
    assert tool_call.model_dump() == {
        "plugin_id": "plugin-1",
        "tool_name": "lookup_entry",
        "arguments": {},
    }

    captured: dict[str, Any] = {}

    async def fake_call_tool(*, user_id: str, plugin_name: str, tool_name: str, arguments: dict[str, Any], timeout: float | None = None, max_reconnect_attempts: int = 2) -> dict[str, Any]:
        captured.update(
            {
                "user_id": user_id,
                "plugin_name": plugin_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "timeout": timeout,
                "max_reconnect_attempts": max_reconnect_attempts,
            }
        )
        return {"ok": True, "args": arguments}

    mcp_client.__dict__["call_tool"] = fake_call_tool
    try:
        result = asyncio.run(
            mcp_client._execute_single_tool_call(
                user_id="user-1",
                tool_call={
                    "id": "call-1",
                    "function": {
                        "name": "lorebook.lookup",
                        "arguments": json.dumps({"query": "月光"}, ensure_ascii=False),
                    },
                },
                timeout=7.5,
            )
        )
    finally:
        mcp_client.__dict__.pop("call_tool", None)

    assert captured == {
        "user_id": "user-1",
        "plugin_name": "lorebook",
        "tool_name": "lookup",
        "arguments": {"query": "月光"},
        "timeout": 7.5,
        "max_reconnect_attempts": 2,
    }
    assert result == {
        "tool_call_id": "call-1",
        "role": "tool",
        "name": "lorebook.lookup",
        "content": json.dumps({"ok": True, "args": {"query": "月光"}}, ensure_ascii=False),
        "success": True,
    }


def test_mcp_router_source_keeps_facade_and_schema_boundary_only() -> None:
    tree = ast.parse(MCP_PLUGINS_FILE.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("app.services.ai_clients") or module.startswith("app.services.ai_providers"):
                imported_modules.add(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.services.ai_clients") or alias.name.startswith("app.services.ai_providers"):
                    imported_modules.add(alias.name)

    direct_sdk_constructors = {
        call.func.id
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in {"OpenAIClient", "AnthropicClient", "GeminiClient", "AsyncOpenAI", "AsyncAnthropic", "ClientSession"}
    }

    assert imported_modules == set()
    assert direct_sdk_constructors == set()
