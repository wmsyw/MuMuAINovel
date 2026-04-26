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
from app.models import Career, Chapter, Character, OrganizationEntity, Project, RelationshipTimelineEvent
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
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


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


USER_ID = "user-timeline-api"
PROJECT_ID = "project-timeline-api"


class AsyncSessionAdapter:
    """Tiny async facade over a sync Session for FastAPI route tests."""

    def __init__(self, session: Session) -> None:
        self.session: SyncSessionProtocol = cast(SyncSessionProtocol, session)

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return self.session.execute(*args, **kwargs)

    async def run_sync(self, fn: Callable[[Session], RunSyncT]) -> RunSyncT:
        return fn(cast(Session, self.session))

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()


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
        return SimpleNamespace(id=user_id, username="timeline-user", trust_level=1, is_admin=False)

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


def _seed_timeline(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="时间线 API"))
        session.add(Project(id="project-timeline-other", user_id="user-other", title="其他时间线"))
        session.add_all(
            [
                Chapter(id="chapter-api-1", project_id=PROJECT_ID, chapter_number=1, title="第一章", sub_index=1, content="初遇"),
                Chapter(id="chapter-api-5", project_id=PROJECT_ID, chapter_number=5, title="第五章", sub_index=5, content="转折"),
                Chapter(id="chapter-api-9", project_id=PROJECT_ID, chapter_number=9, title="第九章", sub_index=9, content="余波"),
            ]
        )
        session.add_all(
            [
                Character(id="char-lin-api", project_id=PROJECT_ID, name="林青岚"),
                Character(id="char-shen-api", project_id=PROJECT_ID, name="沈砚"),
                OrganizationEntity(id="org-xunxing-api", project_id=PROJECT_ID, name="巡星司", normalized_name="巡星司"),
                OrganizationEntity(id="org-xingtu-api", project_id=PROJECT_ID, name="星图会", normalized_name="星图会"),
                Career(id="career-sword-api", project_id=PROJECT_ID, name="剑修", type="main", stages="[]", max_stage=9),
                Career(id="career-star-api", project_id=PROJECT_ID, name="星术师", type="main", stages="[]", max_stage=6),
            ]
        )
        session.add_all(
            [
                _event(
                    "event-rel-ally",
                    event_type="relationship",
                    relationship_name="盟友",
                    character_id="char-lin-api",
                    related_character_id="char-shen-api",
                    valid_from_chapter_id="chapter-api-1",
                    valid_from_chapter_order=1,
                    valid_to_chapter_id="chapter-api-5",
                    valid_to_chapter_order=5,
                ),
                _event(
                    "event-rel-rival",
                    event_type="relationship",
                    relationship_name="敌对盟友",
                    character_id="char-lin-api",
                    related_character_id="char-shen-api",
                    valid_from_chapter_id="chapter-api-5",
                    valid_from_chapter_order=5,
                ),
                _event(
                    "event-aff-old",
                    event_type="affiliation",
                    character_id="char-lin-api",
                    organization_entity_id="org-xunxing-api",
                    position="外勤",
                    valid_from_chapter_id="chapter-api-1",
                    valid_from_chapter_order=1,
                    valid_to_chapter_id="chapter-api-5",
                    valid_to_chapter_order=5,
                ),
                _event(
                    "event-aff-new",
                    event_type="affiliation",
                    character_id="char-lin-api",
                    organization_entity_id="org-xingtu-api",
                    position="顾问",
                    valid_from_chapter_id="chapter-api-5",
                    valid_from_chapter_order=5,
                ),
                _event(
                    "event-prof-old",
                    event_type="profession",
                    character_id="char-lin-api",
                    career_id="career-sword-api",
                    career_stage=2,
                    valid_from_chapter_id="chapter-api-1",
                    valid_from_chapter_order=1,
                    valid_to_chapter_id="chapter-api-5",
                    valid_to_chapter_order=5,
                ),
                _event(
                    "event-prof-new",
                    event_type="profession",
                    character_id="char-lin-api",
                    career_id="career-star-api",
                    career_stage=4,
                    valid_from_chapter_id="chapter-api-5",
                    valid_from_chapter_order=5,
                ),
                _event(
                    "event-rolled-back",
                    event_type="relationship",
                    event_status="rolled_back",
                    relationship_name="误抽取",
                    character_id="char-lin-api",
                    related_character_id="char-shen-api",
                    valid_from_chapter_id="chapter-api-9",
                    valid_from_chapter_order=9,
                ),
            ]
        )
        session.commit()


def _event(
    event_id: str,
    *,
    event_type: str,
    event_status: str = "active",
    relationship_name: str | None = None,
    character_id: str | None = None,
    related_character_id: str | None = None,
    organization_entity_id: str | None = None,
    career_id: str | None = None,
    position: str | None = None,
    career_stage: int | None = None,
    valid_from_chapter_id: str | None = None,
    valid_from_chapter_order: int | None = None,
    valid_to_chapter_id: str | None = None,
    valid_to_chapter_order: int | None = None,
) -> RelationshipTimelineEvent:
    return RelationshipTimelineEvent(
        id=event_id,
        project_id=PROJECT_ID,
        event_type=event_type,
        event_status=event_status,
        relationship_name=relationship_name,
        character_id=character_id,
        related_character_id=related_character_id,
        organization_entity_id=organization_entity_id,
        career_id=career_id,
        position=position,
        career_stage=career_stage,
        source_chapter_id=valid_from_chapter_id,
        source_chapter_order=valid_from_chapter_order,
        valid_from_chapter_id=valid_from_chapter_id,
        valid_from_chapter_order=valid_from_chapter_order,
        valid_to_chapter_id=valid_to_chapter_id,
        valid_to_chapter_order=valid_to_chapter_order,
        evidence_text=relationship_name or position or career_id,
        confidence=0.95,
    )


def test_timeline_router_is_registered_and_returns_chapter_specific_state(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_timeline(session_factory)

    registered_paths = {route.path for route in app.routes}
    assert "/api/timeline/projects/{project_id}/state" in registered_paths
    assert "/api/timeline/projects/{project_id}/history" in registered_paths

    chapter_3 = client.get("/api/timeline/projects/project-timeline-api/state", params={"chapter_number": 3})
    chapter_6 = client.get("/api/timeline/projects/project-timeline-api/state", params={"chapter_id": "chapter-api-5", "chapter_order": 6})

    assert chapter_3.status_code == 200
    state_3 = chapter_3.json()
    assert state_3["project_id"] == PROJECT_ID
    assert state_3["point"] == {"chapter_id": None, "chapter_number": 3, "chapter_order": 3}
    assert [event["relationship_name"] for event in state_3["relationships"]] == ["盟友"]
    assert [(event["organization_entity_id"], event["position"]) for event in state_3["affiliations"]] == [("org-xunxing-api", "外勤")]
    assert [(event["career_id"], event["career_stage"]) for event in state_3["professions"]] == [("career-sword-api", 2)]

    assert chapter_6.status_code == 200
    state_6 = chapter_6.json()
    assert state_6["point"] == {"chapter_id": "chapter-api-5", "chapter_number": 5, "chapter_order": 6}
    assert [event["relationship_name"] for event in state_6["relationships"]] == ["敌对盟友"]
    assert [(event["organization_entity_id"], event["position"]) for event in state_6["affiliations"]] == [("org-xingtu-api", "顾问")]
    assert [(event["career_id"], event["career_stage"]) for event in state_6["professions"]] == [("career-star-api", 4)]


def test_timeline_history_excludes_rolled_back_events_and_checks_project_ownership(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_timeline(session_factory)

    history = client.get("/api/timeline/projects/project-timeline-api/history", params={"event_type": "relationship"})
    forbidden = client.get("/api/timeline/projects/project-timeline-other/state", params={"chapter_number": 1})

    assert history.status_code == 200
    payload = history.json()
    assert payload["total"] == 2
    assert [event["id"] for event in payload["items"]] == ["event-rel-ally", "event-rel-rival"]
    assert all(event["event_status"] != "rolled_back" for event in payload["items"])
    assert forbidden.status_code == 404


def test_openapi_schema_generation_includes_timeline_paths(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, _ = api_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/timeline/projects/{project_id}/state" in paths
    assert "/api/timeline/projects/{project_id}/history" in paths
