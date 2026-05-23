from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false

import pytest
import sys
import types
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Project
from app.models.lorebook import LorebookEntry


DEFAULT_TEST_PROJECT_ID = "project-test-default"
DEFAULT_TEST_USER_ID = "user-test-default"


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


async def _seed_lorebook_fixture(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async with async_db_session() as session:
        session.add(Project(id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="龙城风雨"))
        session.add_all(
            [
                LorebookEntry(
                    id="lore-order",
                    project_id=DEFAULT_TEST_PROJECT_ID,
                    user_id=DEFAULT_TEST_USER_ID,
                    title="青岚阁",
                    content="青岚阁只在暴雨夜打开山门。",
                    activation_keys=["青岚阁"],
                    priority=30,
                    source_type="imported",
                ),
                LorebookEntry(
                    id="lore-city",
                    project_id=DEFAULT_TEST_PROJECT_ID,
                    user_id=DEFAULT_TEST_USER_ID,
                    title="龙城",
                    content="龙城建立在七层玄铁城墙之上。",
                    activation_keys=["龙城"],
                    priority=20,
                    source_type="manual",
                ),
                LorebookEntry(
                    id="lore-disabled",
                    project_id=DEFAULT_TEST_PROJECT_ID,
                    user_id=DEFAULT_TEST_USER_ID,
                    title="禁用条目",
                    content="这段不应出现。",
                    activation_keys=["龙城"],
                    priority=100,
                    enabled=False,
                ),
            ]
        )
        await session.commit()


async def test_preview_includes_selected_ids_and_trace(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_lorebook_fixture(async_db_session)

    response = await test_client.post(
        f"/api/lorebook/projects/{DEFAULT_TEST_PROJECT_ID}/prompt-preview",
        json={"activation_text": "青岚阁派人前往龙城。", "max_tokens": 12, "chars_per_token": 2},
    )

    assert response.status_code == 200
    trace = response.json()["trace"]
    assert trace["source_type"] == "lorebook"
    assert trace["selected_lore_ids"] == ["lore-order", "lore-city"]
    assert trace["budget_estimate"] == {
        "chars_used": 24,
        "budget_chars": 24,
        "estimated_tokens": 12,
        "chars_per_token": 2,
    }
    assert [(item["order"], item["id"], item["source_type"]) for item in trace["items"]] == [
        (1, "lore-order", "lorebook"),
        (2, "lore-city", "lorebook"),
    ]
    assert trace["items"][0]["entry_source_type"] == "imported"
    assert "lore-disabled" not in trace["selected_lore_ids"]
    assert trace["final_preview_text"] == (
        "### 1. 青岚阁 [lore-order]\n"
        "来源: lorebook/imported\n"
        "匹配关键词: 青岚阁\n"
        "青岚阁只在暴雨夜打开山门。\n\n"
        "### 2. 龙城 [lore-city]\n"
        "来源: lorebook/manual\n"
        "匹配关键词: 龙城\n"
        "龙城建立在七层玄铁城…"
    )


async def test_preview_denies_cross_user_project(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
) -> None:
    async with async_db_session() as session:
        session.add(Project(id="project-other-user", user_id="other-user", title="他人项目"))
        await session.commit()

    response = await test_client.post(
        "/api/lorebook/projects/project-other-user/prompt-preview",
        json={"activation_text": "龙城"},
    )

    assert response.status_code == 404
