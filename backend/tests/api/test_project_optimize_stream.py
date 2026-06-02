from __future__ import annotations

import json
import sys
import types
from typing import cast
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Character, Outline, Project


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


class _StubEmailService:
    async def send_mail(self, **_: object) -> None:
        return None


class _StubMemoryService:
    async def delete_project_memories(self, *_: object) -> None:
        return None


_email_service_stub = types.ModuleType("app.services.email_service")
setattr(_email_service_stub, "email_service", _StubEmailService())
_ = sys.modules.setdefault("app.services.email_service", _email_service_stub)

_memory_service_stub = types.ModuleType("app.services.memory_service")
setattr(_memory_service_stub, "memory_service", _StubMemoryService())
_ = sys.modules.setdefault("app.services.memory_service", _memory_service_stub)


pytestmark = pytest.mark.anyio


PROJECT_ID = "project-optimize-stream"
USER_ID = "user-test-default"


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _sse_payloads(text: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for block in text.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line.removeprefix("data: ")))
    return payloads


def _sse_result(text: str) -> dict[str, object]:
    for payload in _sse_payloads(text):
        if payload.get("type") == "result" and isinstance(payload.get("data"), dict):
            return cast(dict[str, object], payload["data"])
    raise AssertionError("SSE result payload not found")


async def _seed_project_context(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str = PROJECT_ID,
    user_id: str = USER_ID,
) -> None:
    async with session_factory() as session:
        session.add(
            Project(
                id=project_id,
                user_id=user_id,
                title="旧标题",
                description="旧简介",
                theme="旧主题",
                genre="科幻",
                world_time_period="近未来",
                world_location="月面城市",
                world_atmosphere="冷峻",
                world_rules="能源严格配给",
                narrative_perspective="第三人称",
            )
        )
        session.add(
            Outline(
                id=f"outline-{project_id}",
                project_id=project_id,
                title="第一幕",
                content="主角在月面城市发现能源配给系统隐藏着失踪者记忆交易的秘密。" * 5,
                order_index=1,
            )
        )
        session.add(
            Character(
                id=f"character-{project_id}",
                project_id=project_id,
                name="林澈",
                role_type="protagonist",
                personality="冷静、克制，但无法放弃寻找真相。",
                background="失踪工程师的孩子。",
            )
        )
        await session.commit()


async def test_project_optimize_stream_filters_non_whitelisted_ai_fields(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    mock_ai_service: AsyncMock,
) -> None:
    await _seed_project_context(async_db_session)
    mock_ai_service.return_value = {
        "fields": {
            "title": {"value": "月面残响", "reason": "更贴合记忆交易主线。"},
            "target_words": {"value": "999999", "reason": "非法业务字段。"},
            "theme": {"value": "", "reason": "空值应丢弃。"},
        },
        "reply": "建议收束标题，使其更贴合月面与记忆主题。",
    }

    response = await test_client.post(
        f"/api/projects/{PROJECT_ID}/optimize-stream",
        json={"requirement": "标题更有悬疑感", "conversation_history": [], "current_draft": {}},
    )

    assert response.status_code == 200
    result = _sse_result(response.text)
    fields = cast(dict[str, object], result["fields"])
    assert fields == {
        "title": {"value": "月面残响", "reason": "更贴合记忆交易主线。"}
    }
    assert "target_words" not in fields
    assert "theme" not in fields
    assert result["reply"] == "建议收束标题，使其更贴合月面与记忆主题。"
    assert mock_ai_service.call_count == 1


async def test_project_optimize_stream_auth_fail_before_ai_call(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    mock_ai_service: AsyncMock,
) -> None:
    await _seed_project_context(async_db_session, project_id="project-owned-by-other", user_id="other-user")

    response = await test_client.post(
        "/api/projects/project-owned-by-other/optimize-stream",
        json={"requirement": "尝试越权优化"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "项目不存在或无权访问"
    assert mock_ai_service.call_count == 0


async def test_project_optimize_stream_does_not_mutate_project_record(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    mock_ai_service: AsyncMock,
) -> None:
    await _seed_project_context(async_db_session)
    mock_ai_service.return_value = {
        "fields": {
            "title": {"value": "AI建议标题", "reason": "测试建议不应直接写回。"},
            "description": {"value": "AI建议简介", "reason": "测试建议不应直接写回。"},
        },
        "reply": "仅返回建议，不保存项目。",
    }

    response = await test_client.post(
        f"/api/projects/{PROJECT_ID}/optimize-stream",
        json={"requirement": "优化但不要保存"},
    )

    assert response.status_code == 200
    result = _sse_result(response.text)
    fields = cast(dict[str, dict[str, str]], result["fields"])
    assert fields["title"]["value"] == "AI建议标题"

    async with async_db_session() as session:
        project = (
            await session.execute(select(Project).where(Project.id == PROJECT_ID))
        ).scalar_one()

    assert project.title == "旧标题"
    assert project.description == "旧简介"
    assert project.theme == "旧主题"
    assert project.genre == "科幻"
    assert project.world_time_period == "近未来"
    assert project.world_location == "月面城市"
    assert project.world_atmosphere == "冷峻"
    assert project.world_rules == "能源严格配给"
    assert project.narrative_perspective == "第三人称"
