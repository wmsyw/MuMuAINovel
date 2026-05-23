from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false

import sys
import types

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import CreativeSession, Project, VoicePersona


DEFAULT_TEST_PROJECT_ID = "project-test-default"
DEFAULT_TEST_USER_ID = "user-test-default"
SESSION_ID = "session-voice-persona-default"


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


async def _seed_projects_and_session(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async with async_db_session() as session:
        session.add(Project(id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="声音画像项目"))
        session.add(Project(id="project-other-same-user", user_id=DEFAULT_TEST_USER_ID, title="同作者其他项目"))
        session.add(Project(id="project-other-user", user_id="other-user", title="他人项目"))
        session.add(CreativeSession(id=SESSION_ID, project_id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="声音试写间"))
        session.add(CreativeSession(id="session-other-project", project_id="project-other-same-user", user_id=DEFAULT_TEST_USER_ID, title="其他项目试写间"))
        await session.commit()


def _enable_voice_personas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.voice_personas.feature_flags.is_enabled", lambda flag_name: flag_name == "voice_personas_enabled")


async def test_create_session_scoped_voice_persona_and_preview_trace(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_voice_personas(monkeypatch)
    await _seed_projects_and_session(async_db_session)

    create_response = await test_client.post(
        f"/api/voice-personas/projects/{DEFAULT_TEST_PROJECT_ID}",
        json={
            "name": "冷峻雨夜旁白",
            "tone": "冷静、压迫、留白",
            "style": "短句推进，少解释，多动作",
            "point_of_view": "第三人称限知",
            "constraints": "不要作者跳出点评；不要替角色解释动机。",
            "session_id": SESSION_ID,
            "sort_order": 2,
            "enabled": True,
            "user_id": "client-user-must-be-ignored",
        },
    )
    assert create_response.status_code == 200
    persona = create_response.json()
    assert persona["project_id"] == DEFAULT_TEST_PROJECT_ID
    assert persona["user_id"] == DEFAULT_TEST_USER_ID
    assert persona["scope"] == "session"
    assert persona["session_id"] == SESSION_ID

    list_response = await test_client.get(f"/api/voice-personas/projects/{DEFAULT_TEST_PROJECT_ID}", params={"session_id": SESSION_ID})
    assert list_response.status_code == 200
    assert [item["name"] for item in list_response.json()["items"]] == ["冷峻雨夜旁白"]

    preview_response = await test_client.post(
        f"/api/voice-personas/projects/{DEFAULT_TEST_PROJECT_ID}/prompt-preview",
        json={
            "persona_id": persona["id"],
            "session_id": SESSION_ID,
            "base_prompt": "原始提示词",
            "injection_enabled": True,
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    trace = preview["trace"]
    assert trace["source_type"] == "voice_persona"
    assert trace["selected_voice_persona_id"] == persona["id"]
    assert trace["profile"]["point_of_view"] == "第三人称限知"
    assert trace["items"][0]["order"] == 1
    assert trace["items"][0]["trace_id"] == trace["trace_id"]
    assert "<voice_persona_context" in preview["preview_prompt"]
    assert "不要作者跳出点评" in preview["preview_prompt"]

    async with async_db_session() as session:
        count_result = await session.execute(select(func.count(VoicePersona.id)))
        assert count_result.scalar_one() == 1


async def test_cross_project_persona_denied(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_voice_personas(monkeypatch)
    await _seed_projects_and_session(async_db_session)

    create_response = await test_client.post(
        f"/api/voice-personas/projects/{DEFAULT_TEST_PROJECT_ID}",
        json={
            "name": "项目A旁白",
            "tone": "克制",
            "style": "冷静叙述",
            "point_of_view": "第三人称",
            "constraints": "只作为写作声音参考。",
        },
    )
    assert create_response.status_code == 200
    persona_id = create_response.json()["id"]

    denied_response = await test_client.post(
        "/api/voice-personas/projects/project-other-same-user/prompt-preview",
        json={"persona_id": persona_id, "base_prompt": "其他项目提示词", "injection_enabled": True},
    )
    assert denied_response.status_code in {403, 404}

    cross_session_response = await test_client.post(
        f"/api/voice-personas/projects/{DEFAULT_TEST_PROJECT_ID}",
        json={
            "name": "错误会话画像",
            "tone": "克制",
            "session_id": "session-other-project",
        },
    )
    assert cross_session_response.status_code in {403, 404}
