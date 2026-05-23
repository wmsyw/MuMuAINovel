from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportPrivateUsage=false, reportMissingParameterType=false, reportUnknownLambdaType=false, reportUnusedCallResult=false

import json
import sys
import types
from collections import defaultdict
from datetime import datetime
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

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

    setattr(_streamable_stub, "streamablehttp_client", lambda **k: _StubContext())
    setattr(_sse_stub, "sse_client", lambda **k: _StubContext())
    sys.modules["mcp"] = _mcp_stub
    sys.modules["mcp.client"] = _client_stub
    sys.modules["mcp.client.streamable_http"] = _streamable_stub
    sys.modules["mcp.client.sse"] = _sse_stub

sys.modules["app.services.memory_service"] = MagicMock()
sys.modules["app.services.email_service"] = MagicMock()

from app.main import app as fastapi_app
from app.api.mcp_plugins import require_admin
from app.mcp.facade import ToolMetrics, mcp_client
from app.user_manager import User


@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield client


def override_require_admin() -> Any:
    def _override(request: Request):
        user = User(
            user_id="admin-user",
            username="admin",
            display_name="Admin User",
            is_admin=True,
            linuxdo_id="123",
            created_at="2024-01-01",
            last_login="2024-01-01",
        )
        request.state.user = user
        request.state.user_id = user.user_id
        request.state.is_admin = user.is_admin
        return user

    return _override


@pytest.mark.anyio
async def test_mcp_admin_stats_are_sanitized(api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fastapi_app.dependency_overrides[require_admin] = override_require_admin()
    try:
        cache_entries = {
            "alice:writer": types.SimpleNamespace(
                tools=[{"name": "tool-a"}],
                hit_count=3,
                expire_time=datetime(2026, 1, 1, 12, 0, 0),
            ),
            "bob:reader": types.SimpleNamespace(
                tools=[{"name": "tool-b"}, {"name": "tool-c"}],
                hit_count=4,
                expire_time=datetime(2026, 1, 1, 13, 0, 0),
            ),
        }
        session_entries = {
            "alice:plugin-a": types.SimpleNamespace(
                status="active",
                request_count=5,
                error_count=1,
                error_rate=0.2,
                url="https://alice.example/mcp",
                created_at=1700000000.0,
                last_access=1700000300.0,
            ),
            "bob:plugin-b": types.SimpleNamespace(
                status="degraded",
                request_count=7,
                error_count=2,
                error_rate=0.286,
                url="https://bob.example/mcp",
                created_at=1700001000.0,
                last_access=1700001300.0,
            ),
        }
        metrics_entries = defaultdict(ToolMetrics)
        metrics_entries["alice-tool"].record_success(12.5)
        metrics_entries["bob-tool"].record_failure(7.5)

        monkeypatch.setattr(mcp_client, "_tool_cache", cache_entries, raising=False)
        monkeypatch.setattr(mcp_client, "_sessions", session_entries, raising=False)
        monkeypatch.setattr(mcp_client, "_metrics", metrics_entries, raising=False)

        metrics_response = await api_client.get("/api/mcp/plugins/metrics")
        assert metrics_response.status_code == 200
        metrics_payload = metrics_response.json()
        assert metrics_payload["tool_name"] is None
        assert metrics_payload["metrics"]["total_tools"] == 2
        assert metrics_payload["metrics"]["total_calls"] == 2

        cache_response = await api_client.get("/api/mcp/plugins/cache/stats")
        assert cache_response.status_code == 200
        cache_payload = cache_response.json()["cache_stats"]
        assert cache_payload["total_entries"] == 2
        assert cache_payload["total_hits"] == 7
        assert "entries" not in cache_payload

        session_response = await api_client.get("/api/mcp/plugins/sessions/stats")
        assert session_response.status_code == 200
        session_payload = session_response.json()["session_stats"]
        assert session_payload["total_sessions"] == 2
        assert session_payload["status_counts"] == {"active": 1, "degraded": 1}
        assert "sessions" not in session_payload

        combined_payload = json.dumps({
            "metrics": metrics_payload,
            "cache_stats": cache_payload,
            "session_stats": session_payload,
        }, ensure_ascii=False)
        assert "alice:writer" not in combined_payload
        assert "bob:reader" not in combined_payload
        assert "alice:plugin-a" not in combined_payload
        assert "bob:plugin-b" not in combined_payload
        assert "https://alice.example/mcp" not in combined_payload
        assert "https://bob.example/mcp" not in combined_payload
    finally:
        fastapi_app.dependency_overrides.clear()
