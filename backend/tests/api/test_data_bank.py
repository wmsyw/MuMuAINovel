from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false

import sys
import types

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Project


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


async def _seed_data_bank_projects(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async with async_db_session() as session:
        session.add_all(
            [
                Project(id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="资料库API项目"),
                Project(id="project-other-user", user_id="other-user", title="他人项目"),
            ]
        )
        await session.commit()


async def test_ingest_and_retrieve_note_with_trace(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_data_bank_projects(async_db_session)

    snippet_response = await test_client.post(
        f"/api/memories/projects/{DEFAULT_TEST_PROJECT_ID}/data-bank/snippets",
        json={
            "title": "青岚阁片段",
            "text": "青岚阁只在暴雨夜打开山门。龙城来使必须等待三声钟响。",
            "user_id": "client-user-must-be-ignored",
        },
    )
    assert snippet_response.status_code == 200
    snippet = snippet_response.json()
    assert snippet["project_id"] == DEFAULT_TEST_PROJECT_ID
    assert snippet["user_id"] == DEFAULT_TEST_USER_ID
    assert snippet["source_type"] == "snippet"
    assert snippet["chunk_count"] == 1

    upload_response = await test_client.post(
        f"/api/memories/projects/{DEFAULT_TEST_PROJECT_ID}/data-bank/uploads",
        data={"title": "龙城上传资料"},
        files={"file": ("dragon.md", "# 龙城\n龙城建立在七层玄铁城墙之上。", "text/markdown")},
    )
    assert upload_response.status_code == 200
    upload = upload_response.json()
    assert upload["source_type"] == "upload"
    assert upload["filename"] == "dragon.md"

    retrieval_response = await test_client.post(
        f"/api/memories/projects/{DEFAULT_TEST_PROJECT_ID}/data-bank/retrieve",
        json={"query": "青岚阁 龙城", "limit": 5},
    )
    assert retrieval_response.status_code == 200
    trace = retrieval_response.json()
    assert trace["strategy"] == "deterministic-lexical-v1"
    assert trace["project_id"] == DEFAULT_TEST_PROJECT_ID
    assert trace["returned_count"] == 2
    assert [result["order"] for result in trace["results"]] == [1, 2]
    assert trace["results"][0]["source_type"] == "data_bank"
    assert trace["results"][0]["item_source_type"] == "snippet"
    assert trace["results"][0]["score"] > 0
    assert trace["results"][0]["item_id"] == snippet["id"]
    assert trace["results"][0]["chunk_id"]
    assert trace["results"][0]["matched_terms"]
    assert trace["results"][0]["char_start"] == 0
    assert trace["results"][0]["char_end"] == len("青岚阁只在暴雨夜打开山门。龙城来使必须等待三声钟响。")
    assert trace["results"][0]["content_hash"]
    assert "青岚阁" in trace["results"][0]["content"]


async def test_remote_url_ingestion_rejected(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_data_bank_projects(async_db_session)

    remote_response = await test_client.post(
        f"/api/memories/projects/{DEFAULT_TEST_PROJECT_ID}/data-bank/snippets",
        json={
            "title": "远程资料",
            "text": "不应入库",
            "source_url": "https://example.com/book.md",
        },
    )
    assert remote_response.status_code in {400, 422}
    assert "不支持远程URL导入" in remote_response.json()["detail"]

    remote_alias_response = await test_client.post(
        f"/api/memories/projects/{DEFAULT_TEST_PROJECT_ID}/data-bank/snippets",
        json={
            "title": "远程资料别名",
            "text": "同样不应入库",
            "remote_url": "https://example.com/remote.md",
        },
    )
    assert remote_alias_response.status_code in {400, 422}

    list_response = await test_client.get(f"/api/memories/projects/{DEFAULT_TEST_PROJECT_ID}/data-bank")
    assert list_response.status_code == 200
    assert list_response.json() == {"total": 0, "items": []}

    retrieval_response = await test_client.post(
        f"/api/memories/projects/{DEFAULT_TEST_PROJECT_ID}/data-bank/retrieve",
        json={"query": "不应入库", "limit": 5},
    )
    assert retrieval_response.status_code == 200
    trace = retrieval_response.json()
    assert trace["project_id"] == DEFAULT_TEST_PROJECT_ID
    assert trace["total_candidates"] == 0
    assert trace["returned_count"] == 0
    assert trace["results"] == []


async def test_cross_project_retrieve_denied(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_data_bank_projects(async_db_session)

    denied_response = await test_client.post(
        "/api/memories/projects/project-other-user/data-bank/retrieve",
        json={"query": "任何内容"},
    )
    assert denied_response.status_code == 404
