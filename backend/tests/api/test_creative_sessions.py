from __future__ import annotations

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportPrivateLocalImportUsage=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
import sys
import types
from types import SimpleNamespace
from typing import Protocol, TypeVar, cast

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.middleware import auth_middleware
from app.models import Chapter, PlotAnalysis, Project, StoryMemory
from app.security import create_session_token


RunSyncT = TypeVar("RunSyncT")
ScalarT = TypeVar("ScalarT", covariant=True)


class ScalarResultProtocol(Protocol[ScalarT]):
    def all(self) -> Sequence[ScalarT]: ...


class ExecuteResultProtocol(Protocol):
    def scalar_one(self) -> object: ...
    def scalar_one_or_none(self) -> object | None: ...
    def scalars(self) -> ScalarResultProtocol[object]: ...
    def all(self) -> Sequence[object]: ...


class SyncSessionProtocol(Protocol):
    def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol: ...
    def add(self, instance: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def refresh(self, instance: object) -> None: ...
    def delete(self, instance: object) -> None: ...


if "mcp" not in sys.modules:
    _mcp_stub = types.ModuleType("mcp")
    setattr(_mcp_stub, "ClientSession", type("ClientSession", (), {}))
    setattr(_mcp_stub, "types", SimpleNamespace(TextContent=type("TextContent", (), {}), ImageContent=type("ImageContent", (), {})))
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
setattr(_memory_service_stub, "memory_service", SimpleNamespace())
_ = sys.modules.setdefault("app.services.memory_service", _memory_service_stub)


class _StubEmailService:
    async def send_mail(self, **_: object) -> None:
        return None


_email_service_stub = types.ModuleType("app.services.email_service")
setattr(_email_service_stub, "email_service", _StubEmailService())
_ = sys.modules.setdefault("app.services.email_service", _email_service_stub)

from app.main import app


USER_ID = "user-creative-owner"
OTHER_USER_ID = "user-creative-intruder"
PROJECT_ID = "project-creative-owner"
OTHER_PROJECT_ID = "project-creative-other"


class AsyncSessionAdapter:
    """Tiny async facade over a sync Session for FastAPI route tests."""

    def __init__(self, session: Session) -> None:
        self.session: SyncSessionProtocol = cast(SyncSessionProtocol, session)

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return self.session.execute(*args, **kwargs)

    async def run_sync(self, fn: Callable[[Session], RunSyncT]) -> RunSyncT:
        return fn(cast(Session, self.session))

    def add(self, instance: object) -> None:
        self.session.add(instance)

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()

    async def refresh(self, instance: object) -> None:
        self.session.refresh(instance)

    async def delete(self, instance: object) -> None:
        self.session.delete(instance)


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

    async def fake_get_user(user_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=user_id, user_id=user_id, username=user_id, trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator[AsyncSessionAdapter]:
        with session_factory() as session:
            yield AsyncSessionAdapter(session)

    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    monkeypatch.setattr("app.api.creative_sessions.feature_flags.is_enabled", lambda flag_name: flag_name == "creative_sessions_enabled")
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", create_session_token(USER_ID, 3600))
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _seed_projects(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="创作会话项目"))
        session.add(Project(id=OTHER_PROJECT_ID, user_id=OTHER_USER_ID, title="他人创作项目"))
        session.commit()


def test_create_resume_and_search(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_projects(session_factory)

    create_response = client.post(
        f"/api/creative-sessions/projects/{PROJECT_ID}",
        json={"title": "Draft Room", "user_id": OTHER_USER_ID, "metadata": {"client": "ignored-user"}},
    )
    assert create_response.status_code == 200
    session_payload = create_response.json()
    assert session_payload["project_id"] == PROJECT_ID
    assert session_payload["user_id"] == USER_ID
    session_id = session_payload["id"]

    first_message = client.post(
        f"/api/creative-sessions/{session_id}/messages",
        json={"role": "user", "content": "Brainstorm a storm-lit opening scene.", "user_id": OTHER_USER_ID},
    )
    assert first_message.status_code == 200
    assert first_message.json()["user_id"] == USER_ID
    assert first_message.json()["position"] == 0

    second_message = client.post(
        f"/api/creative-sessions/{session_id}/messages",
        json={"role": "assistant", "content": "Rain hammers the old gate while the lantern gutters."},
    )
    assert second_message.status_code == 200
    assert second_message.json()["position"] == 1

    reopen_response = client.get(f"/api/creative-sessions/{session_id}")
    assert reopen_response.status_code == 200
    reopened = reopen_response.json()
    assert [message["content"] for message in reopened["messages"]] == [
        "Brainstorm a storm-lit opening scene.",
        "Rain hammers the old gate while the lantern gutters.",
    ]

    search_response = client.get(f"/api/creative-sessions/projects/{PROJECT_ID}/search", params={"query": "storm-lit"})
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total"] == 1
    assert search_payload["items"][0]["content"] == "Brainstorm a storm-lit opening scene."

    with session_factory() as db:
        assert db.query(Chapter).count() == 0
        assert db.query(StoryMemory).count() == 0
        assert db.query(PlotAnalysis).count() == 0


def test_cross_user_session_denied(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_projects(session_factory)

    create_response = client.post(f"/api/creative-sessions/projects/{PROJECT_ID}", json={"title": "Alice Room"})
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    client.cookies.set("session_token", create_session_token(OTHER_USER_ID, 3600))
    denied_reopen = client.get(f"/api/creative-sessions/{session_id}")
    assert denied_reopen.status_code == 404

    denied_search = client.get(f"/api/creative-sessions/projects/{PROJECT_ID}/search", params={"query": "Alice"})
    assert denied_search.status_code == 404


def test_creative_sessions_feature_flag_fails_closed(api_client: tuple[TestClient, sessionmaker[Session]], monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_factory = api_client
    _seed_projects(session_factory)
    monkeypatch.setattr("app.api.creative_sessions.feature_flags.is_enabled", lambda flag_name: False)

    response = client.get(f"/api/creative-sessions/projects/{PROJECT_ID}")
    assert response.status_code == 404
