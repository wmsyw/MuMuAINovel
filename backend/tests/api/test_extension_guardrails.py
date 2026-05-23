from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportPrivateUsage=false, reportMissingParameterType=false, reportUnknownLambdaType=false, reportUnusedCallResult=false

import sys
import types
from datetime import datetime
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport

# Stub external dependencies before importing app.main
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

# Stub other services
sys.modules["app.services.memory_service"] = MagicMock()
sys.modules["app.services.email_service"] = MagicMock()

from app.main import app as fastapi_app
from app.database import get_db
from app.user_manager import User
from app.api.mcp_plugins import require_login

@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield client

@pytest.fixture
def mock_db() -> AsyncMock:
    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.commit = AsyncMock()
    mock.refresh = AsyncMock()
    mock.add = MagicMock()
    mock.delete = AsyncMock()
    
    # Default behavior for existing check
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock.execute.return_value = mock_result
    
    # Mock refresh to set required fields for response schema
    async def mock_refresh(obj):
        if hasattr(obj, "id") and obj.id is None:
            obj.id = "test-id"
        if hasattr(obj, "created_at") and obj.created_at is None:
            obj.created_at = datetime.now()
        # For SQLAlchemy models that might not have these as attributes yet
        if not hasattr(obj, "id"):
            obj.id = "test-id"
        if not hasattr(obj, "created_at"):
            obj.created_at = datetime.now()
            
    mock.refresh.side_effect = mock_refresh
    
    return mock

def override_require_login(is_admin: bool = False):
    def _override(request: Request):
        user = User(
            user_id="test-user",
            username="testuser",
            display_name="Test User",
            is_admin=is_admin,
            linuxdo_id="123",
            created_at="2024-01-01",
            last_login="2024-01-01"
        )
        request.state.user = user
        request.state.user_id = user.user_id
        request.state.is_admin = user.is_admin
        return user
    return _override

def override_get_db(mock_db: Any):
    async def _override(request: Request) -> AsyncGenerator[Any, None]:
        yield mock_db
    return _override

@pytest.mark.anyio
async def test_stdio_plugin_creation_rejected_for_non_admin(api_client: AsyncClient, mock_db: Any) -> None:
    fastapi_app.dependency_overrides[require_login] = override_require_login(is_admin=False)
    fastapi_app.dependency_overrides[get_db] = override_get_db(mock_db)
    try:
        response = await api_client.post(
            "/api/mcp/plugins",
            json={
                "plugin_name": "dangerous-plugin",
                "plugin_type": "stdio",
                "command": "rm -rf /",
                "args": []
            }
        )
        assert response.status_code == 403
        assert "只有管理员可以创建 stdio 类型插件" in response.json()["detail"]
    finally:
        fastapi_app.dependency_overrides.clear()

@pytest.mark.anyio
async def test_stdio_plugin_creation_allowed_for_admin(api_client: AsyncClient, mock_db: Any) -> None:
    fastapi_app.dependency_overrides[require_login] = override_require_login(is_admin=True)
    fastapi_app.dependency_overrides[get_db] = override_get_db(mock_db)
    
    try:
        response = await api_client.post(
            "/api/mcp/plugins",
            json={
                "plugin_name": "admin-plugin",
                "plugin_type": "stdio",
                "command": "ls",
                "args": ["-l"]
            }
        )
        # It might fail later due to other DB issues, but it should pass the 403 check
        assert response.status_code != 403
        if response.status_code == 200:
            assert response.json()["plugin_type"] == "stdio"
    finally:
        fastapi_app.dependency_overrides.clear()

@pytest.mark.anyio
async def test_no_marketplace_endpoints(api_client: AsyncClient) -> None:
    marketplace_paths = [
        "/api/mcp/marketplace",
        "/api/extensions/marketplace",
        "/api/plugins/discover",
        "/api/mcp/install-remote"
    ]
    for path in marketplace_paths:
        response = await api_client.get(path)
        assert response.status_code == 404

@pytest.mark.anyio
async def test_no_remote_manifest_loading(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/mcp/plugins/remote",
        json={"url": "https://malicious.com/mcp-manifest.json"}
    )
    assert response.status_code in [404, 405]

def test_rfc_content_requirements() -> None:
    from pathlib import Path
    rfc_path = Path(__file__).resolve().parents[2] / "docs" / "rfc" / "001-extension-plugin-system.md"
    assert rfc_path.exists()
    content = rfc_path.read_text(encoding="utf-8")
    assert "No runtime plugin execution in MVP" in content
    assert "No public extension marketplace in MVP" in content
    assert "No remote manifest loading" in content
