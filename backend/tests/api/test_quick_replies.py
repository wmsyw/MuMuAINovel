from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false

import sys
import types

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import CreativeSession, CreativeSessionMessage, Project, QuickReply


DEFAULT_TEST_PROJECT_ID = "project-test-default"
DEFAULT_TEST_USER_ID = "user-test-default"
SESSION_ID = "session-quick-reply-default"


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


async def _seed_project_and_session(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async with async_db_session() as session:
        session.add(Project(id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="快捷回复项目"))
        session.add(Project(id="project-other-user", user_id="other-user", title="他人项目"))
        session.add(CreativeSession(id=SESSION_ID, project_id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="片段试写间"))
        await session.commit()


def _enable_quick_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.quick_replies.feature_flags.is_enabled", lambda flag_name: flag_name == "quick_actions_enabled")


async def test_apply_quick_reply_snippet(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_quick_actions(monkeypatch)
    await _seed_project_and_session(async_db_session)

    earlier_response = await test_client.post(
        f"/api/quick-replies/projects/{DEFAULT_TEST_PROJECT_ID}",
        json={
            "label": "前置片段",
            "snippet": "先记录门外的潮湿空气。",
            "sort_order": 1,
            "enabled": True,
            "user_id": "client-user-must-be-ignored",
        },
    )
    assert earlier_response.status_code == 200

    create_response = await test_client.post(
        f"/api/quick-replies/projects/{DEFAULT_TEST_PROJECT_ID}",
        json={
            "label": "雨夜片段",
            "action_type": "safe_snippet",
            "snippet": "雨声打在旧门上，灯影微颤。",
            "sort_order": 2,
            "enabled": True,
            "user_id": "client-user-must-be-ignored",
        },
    )
    assert create_response.status_code == 200
    quick_reply = create_response.json()
    assert quick_reply["project_id"] == DEFAULT_TEST_PROJECT_ID
    assert quick_reply["user_id"] == DEFAULT_TEST_USER_ID
    assert quick_reply["action_type"] == "safe_snippet"

    list_response = await test_client.get(f"/api/quick-replies/projects/{DEFAULT_TEST_PROJECT_ID}")
    assert list_response.status_code == 200
    assert [item["label"] for item in list_response.json()["items"]] == ["前置片段", "雨夜片段"]

    apply_response = await test_client.post(
        f"/api/quick-replies/{quick_reply['id']}/apply",
        json={"session_id": SESSION_ID},
    )
    assert apply_response.status_code == 200
    applied = apply_response.json()
    assert applied["source_type"] == "quick_reply"
    assert applied["action_type"] == "safe_snippet"
    assert applied["trace_label"] == "quick_reply:雨夜片段"
    assert applied["prompt_mutation"] is False
    assert applied["applied_content"] == "雨声打在旧门上，灯影微颤。"
    assert applied["emitted_message"]["content"] == "雨声打在旧门上，灯影微颤。"
    assert applied["emitted_message"]["role"] == "note"
    assert applied["emitted_message"]["metadata"]["trace_label"] == "quick_reply:雨夜片段"
    assert applied["emitted_message"]["metadata"]["prompt_mutation"] is False

    async with async_db_session() as session:
        message_result = await session.execute(select(CreativeSessionMessage).where(CreativeSessionMessage.session_id == SESSION_ID))
        messages = list(message_result.scalars().all())
        assert len(messages) == 1
        assert messages[0].content == "雨声打在旧门上，灯影微颤。"
        assert messages[0].message_metadata["quick_reply_id"] == quick_reply["id"]


async def test_arbitrary_script_macro_rejected(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_quick_actions(monkeypatch)
    await _seed_project_and_session(async_db_session)

    script_action_response = await test_client.post(
        f"/api/quick-replies/projects/{DEFAULT_TEST_PROJECT_ID}",
        json={
            "label": "脚本宏",
            "action_type": "script",
            "snippet": "return fetch('https://example.com')",
            "sort_order": 1,
        },
    )
    assert script_action_response.status_code in {400, 422}

    stscript_response = await test_client.post(
        f"/api/quick-replies/projects/{DEFAULT_TEST_PROJECT_ID}",
        json={
            "label": "STscript宏",
            "action_type": "safe_snippet",
            "snippet": "{{setvar::secret::1}}\n/send 隐藏写入",
            "sort_order": 2,
        },
    )
    assert stscript_response.status_code in {400, 422}

    list_response = await test_client.get(f"/api/quick-replies/projects/{DEFAULT_TEST_PROJECT_ID}")
    assert list_response.status_code == 200
    assert list_response.json() == {"total": 0, "items": []}

    async with async_db_session() as session:
        count_result = await session.execute(select(func.count(QuickReply.id)))
        assert count_result.scalar_one() == 0
