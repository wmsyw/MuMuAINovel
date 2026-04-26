from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from types import SimpleNamespace
from typing import Protocol, TypeVar, cast
import sys
import types

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.middleware import auth_middleware
from app.models import Career, Chapter, Character, Project, RelationshipTimelineEvent
from app.security import create_session_token


RunSyncT = TypeVar("RunSyncT")
ScalarT = TypeVar("ScalarT", covariant=True)


class ScalarResultProtocol(Protocol[ScalarT]):
    def all(self) -> Sequence[ScalarT]: ...


class ExecuteResultProtocol(Protocol):
    def scalar_one(self) -> object: ...
    def scalar_one_or_none(self) -> object | None: ...
    def scalars(self) -> ScalarResultProtocol[object]: ...


class SyncSessionProtocol(Protocol):
    def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol: ...
    def add(self, instance: object) -> None: ...
    def add_all(self, instances: Sequence[object]) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def refresh(self, instance: object) -> None: ...
    def delete(self, instance: object) -> None: ...


class _StubMCPClient:
    async def cleanup(self) -> None:
        return None

    def __getattr__(self, _: str) -> Callable[..., Awaitable[bool]]:
        async def async_noop(*args: object, **kwargs: object) -> bool:
            _ = args
            _ = kwargs
            return False

        return async_noop


class _StubMCPPluginConfig:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


_mcp_stub = types.ModuleType("app.mcp")
setattr(_mcp_stub, "mcp_client", _StubMCPClient())
setattr(_mcp_stub, "MCPPluginConfig", _StubMCPPluginConfig)
setattr(_mcp_stub, "PluginStatus", SimpleNamespace(ACTIVE="active", ERROR="error"))
setattr(_mcp_stub, "register_status_sync", lambda: None)
_ = sys.modules.setdefault("app.mcp", _mcp_stub)

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


USER_ID = "user-profession-api"
PROJECT_ID = "project-profession-api"


class AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self.session: SyncSessionProtocol = cast(SyncSessionProtocol, session)

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return self.session.execute(*args, **kwargs)

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()

    async def refresh(self, instance: object) -> None:
        self.session.refresh(instance)

    async def delete(self, instance: object) -> None:
        self.session.delete(instance)

    def add(self, instance: object) -> None:
        self.session.add(instance)

    async def run_sync(self, fn: Callable[[Session], RunSyncT]) -> RunSyncT:
        return fn(cast(Session, self.session))


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
        return SimpleNamespace(id=user_id, username="profession-user", trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator[AsyncSessionAdapter]:
        with session_factory() as session:
            yield AsyncSessionAdapter(session)

    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", create_session_token(USER_ID, 3600))
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _seed_profession_project(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="职业年表"))
        session.add_all([
            Chapter(id="chapter-prof-1", project_id=PROJECT_ID, chapter_number=1, title="第一章", sub_index=1, content="林青岚是剑修。"),
            Chapter(id="chapter-prof-5", project_id=PROJECT_ID, chapter_number=5, title="第五章", sub_index=5, content="林青岚转为星术师。"),
        ])
        session.add(Character(id="char-prof-lin", project_id=PROJECT_ID, name="林青岚"))
        session.add_all([
            Career(id="career-prof-sword", project_id=PROJECT_ID, name="剑修", type="main", stages='[{"level":1,"name":"初阶"},{"level":2,"name":"二阶"}]', max_stage=2),
            Career(id="career-prof-star", project_id=PROJECT_ID, name="星术师", type="main", stages='[{"level":1,"name":"窥星"},{"level":4,"name":"星桥"}]', max_stage=4),
        ])
        session.commit()


def test_profession_assignment_routes_append_chapter_specific_timeline(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_profession_project(session_factory)

    first = client.post(
        "/api/careers/character/char-prof-lin/careers/main",
        json={
            "career_id": "career-prof-sword",
            "current_stage": 2,
            "source_chapter_id": "chapter-prof-1",
            "source_chapter_order": 1,
            "valid_from_chapter_id": "chapter-prof-1",
            "valid_from_chapter_order": 1,
            "story_time_label": "第一章",
        },
    )
    second = client.post(
        "/api/careers/character/char-prof-lin/careers/main",
        json={
            "career_id": "career-prof-star",
            "current_stage": 4,
            "source_chapter_id": "chapter-prof-5",
            "source_chapter_order": 5,
            "valid_from_chapter_id": "chapter-prof-5",
            "valid_from_chapter_order": 5,
            "story_time_label": "第五章",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    with session_factory() as session:
        events = session.execute(sa.select(RelationshipTimelineEvent).order_by(RelationshipTimelineEvent.valid_from_chapter_order)).scalars().all()
        assert [(event.career_id, event.career_stage, event.valid_to_chapter_id) for event in events] == [
            ("career-prof-sword", 2, "chapter-prof-5"),
            ("career-prof-star", 4, None),
        ]

    state_3 = client.get(f"/api/timeline/projects/{PROJECT_ID}/state", params={"chapter_number": 3})
    state_6 = client.get(f"/api/timeline/projects/{PROJECT_ID}/state", params={"chapter_number": 6})
    assert state_3.status_code == 200
    assert state_6.status_code == 200
    assert [(item["career_id"], item["career_stage"]) for item in state_3.json()["professions"]] == [("career-prof-sword", 2)]
    assert [(item["career_id"], item["career_stage"]) for item in state_6.json()["professions"]] == [("career-prof-star", 4)]

    career_view = client.get(
        "/api/careers/character/char-prof-lin/careers",
        params={"include_timeline": True, "chapter_number": 6},
    )
    assert career_view.status_code == 200
    payload = career_view.json()
    assert payload["main_career"]["career_id"] == "career-prof-star"
    assert [(item["career_id"], item["career_stage"]) for item in payload["timeline_professions"]] == [("career-prof-star", 4)]
