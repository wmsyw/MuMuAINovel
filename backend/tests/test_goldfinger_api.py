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
from app.models import Character, Goldfinger, GoldfingerHistoryEvent, Project
from app.security import create_session_token


RunSyncT = TypeVar("RunSyncT")
ScalarT = TypeVar("ScalarT", covariant=True)


class ScalarResultProtocol(Protocol[ScalarT]):
    def all(self) -> Sequence[ScalarT]: ...
    def first(self) -> ScalarT | None: ...


class ExecuteResultProtocol(Protocol):
    def scalar_one(self) -> object: ...
    def scalar_one_or_none(self) -> object | None: ...
    def scalars(self) -> ScalarResultProtocol[object]: ...
    def all(self) -> Sequence[object]: ...
    def first(self) -> object | None: ...


class SyncSessionProtocol(Protocol):
    def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol: ...
    def add(self, instance: object) -> None: ...
    def add_all(self, instances: Sequence[object]) -> None: ...
    def flush(self) -> None: ...
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


USER_ID = "user-goldfinger-api"
PROJECT_ID = "project-goldfinger-api"
OTHER_PROJECT_ID = "project-goldfinger-other"
OWNER_ID = "char-goldfinger-owner"


class AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self.session: SyncSessionProtocol = cast(SyncSessionProtocol, session)

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return self.session.execute(*args, **kwargs)

    def add(self, instance: object) -> None:
        self.session.add(instance)

    def add_all(self, instances: Sequence[object]) -> None:
        self.session.add_all(instances)

    async def flush(self) -> None:
        self.session.flush()

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()

    async def refresh(self, instance: object) -> None:
        self.session.refresh(instance)

    async def delete(self, instance: object) -> None:
        self.session.delete(instance)

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
        return SimpleNamespace(id=user_id, username="goldfinger-user", trust_level=1, is_admin=False)

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


def _seed_project(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="金手指 API"))
        session.add(Project(id=OTHER_PROJECT_ID, user_id="user-other", title="他人项目"))
        session.add(Character(id=OWNER_ID, project_id=PROJECT_ID, name="林墨", role_type="protagonist"))
        session.commit()


def _seed_goldfinger(session_factory: sessionmaker[Session], *, name: str = "天命系统") -> str:
    with session_factory() as session:
        goldfinger = Goldfinger(
            project_id=PROJECT_ID,
            name=name,
            normalized_name=" ".join(name.strip().lower().split()),
            owner_character_id=OWNER_ID,
            owner_character_name="林墨",
            status="active",
            source="manual",
            created_by=USER_ID,
            updated_by=USER_ID,
        )
        session.add(goldfinger)
        session.commit()
        return str(goldfinger.id)


def _count(session_factory: sessionmaker[Session], model: type[object]) -> int:
    with session_factory() as session:
        return int(session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one())


def test_goldfinger_router_crud_history_export_and_delete(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_project(session_factory)

    registered_paths = {route.path for route in app.routes}
    assert "/api/goldfingers/project/{project_id}" in registered_paths
    assert "/api/goldfingers/{goldfinger_id}/history" in registered_paths
    assert "/api/goldfingers/project/{project_id}/import/dry-run" in registered_paths

    listed_empty = client.get(f"/api/goldfingers/project/{PROJECT_ID}")
    assert listed_empty.status_code == 200
    assert listed_empty.json() == {"total": 0, "items": []}

    created = client.post(
        f"/api/goldfingers/project/{PROJECT_ID}",
        json={
            "name": "天命系统",
            "owner_character_id": OWNER_ID,
            "type": "system",
            "status": "active",
            "summary": "发布任务并发放奖励",
            "rules": {"activation": "濒死"},
            "tasks": [{"title": "三日内救下师姐"}],
            "rewards": [{"name": "悟性提升"}],
            "metadata": {"rarity": "mythic"},
        },
    )
    assert created.status_code == 200
    created_payload = created.json()
    goldfinger_id = created_payload["id"]
    assert created_payload == {
        **created_payload,
        "project_id": PROJECT_ID,
        "name": "天命系统",
        "normalized_name": "天命系统",
        "owner_character_id": OWNER_ID,
        "owner_character_name": "林墨",
        "status": "active",
        "source": "manual",
        "metadata": {"rarity": "mythic"},
    }
    assert _count(session_factory, Goldfinger) == 1
    assert _count(session_factory, GoldfingerHistoryEvent) == 1

    updated = client.put(
        f"/api/goldfingers/{goldfinger_id}",
        json={"status": "cooldown", "summary": "完成任务后进入冷却", "cooldown": {"chapters": 3}},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "cooldown"
    assert updated.json()["cooldown"] == {"chapters": 3}

    detail = client.get(f"/api/goldfingers/{goldfinger_id}")
    history = client.get(f"/api/goldfingers/{goldfinger_id}/history")
    assert detail.status_code == 200
    assert detail.json()["summary"] == "完成任务后进入冷却"
    assert history.status_code == 200
    history_payload = history.json()
    assert history_payload["total"] == 2
    assert {event["source_type"] for event in history_payload["items"]} == {"manual"}
    events_by_type = {event["event_type"]: event for event in history_payload["items"]}
    assert set(events_by_type) == {"created", "updated"}
    assert events_by_type["created"]["new_value"]["name"] == "天命系统"
    assert events_by_type["updated"]["old_value"]["status"] == "active"
    assert events_by_type["updated"]["new_value"]["status"] == "cooldown"

    exported = client.get(f"/api/goldfingers/project/{PROJECT_ID}/export")
    assert exported.status_code == 200
    export_payload = exported.json()
    assert export_payload["version"] == "goldfinger-card.v1"
    assert export_payload["export_type"] == "goldfingers"
    assert export_payload["count"] == 1
    assert export_payload["data"][0] == {
        **export_payload["data"][0],
        "name": "天命系统",
        "status": "cooldown",
        "metadata": {"rarity": "mythic"},
    }

    deleted = client.delete(f"/api/goldfingers/{goldfinger_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"message": "金手指删除成功", "id": goldfinger_id}
    assert _count(session_factory, Goldfinger) == 0


def test_goldfinger_import_dry_run_reports_conflicts_without_writes(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_project(session_factory)
    existing_id = _seed_goldfinger(session_factory)
    before_goldfingers = _count(session_factory, Goldfinger)
    before_history = _count(session_factory, GoldfingerHistoryEvent)

    response = client.post(
        f"/api/goldfingers/project/{PROJECT_ID}/import/dry-run",
        json={
            "version": "goldfinger-card.v1",
            "export_type": "goldfingers",
            "count": 2,
            "data": [
                {"name": "天命系统", "status": "active"},
                {"name": "星火戒指", "status": "latent"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["statistics"] == {"total": 2, "creatable": 1, "conflicts": 1, "errors": 0}
    assert payload["conflicts"] == [
        {
            "index": 0,
            "name": "天命系统",
            "normalized_name": "天命系统",
            "existing_id": existing_id,
            "reason": "normalized_name_conflict",
        }
    ]
    assert payload["would_create"] == [{"index": 1, "name": "星火戒指", "normalized_name": "星火戒指"}]
    assert _count(session_factory, Goldfinger) == before_goldfingers
    assert _count(session_factory, GoldfingerHistoryEvent) == before_history


def test_goldfinger_import_apply_creates_rows_and_import_history(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_project(session_factory)

    import_payload = {
        "version": "goldfinger-card.v1",
        "export_type": "goldfingers",
        "count": 2,
        "data": [
            {
                "name": "星火戒指",
                "owner_character_id": OWNER_ID,
                "type": "artifact",
                "status": "latent",
                "summary": "储存星火",
                "rewards": [{"name": "星火护盾"}],
                "metadata": {"source_book": "fixture"},
            },
            {"name": "洞察之眼", "owner_character_name": "未知旅人", "type": "ability", "status": "active"},
        ],
    }
    dry_run = client.post(f"/api/goldfingers/project/{PROJECT_ID}/import/dry-run", json=import_payload)
    assert dry_run.status_code == 200
    assert dry_run.json()["valid"] is True
    assert _count(session_factory, Goldfinger) == 0
    assert _count(session_factory, GoldfingerHistoryEvent) == 0

    imported = client.post(f"/api/goldfingers/project/{PROJECT_ID}/import", json=import_payload)
    assert imported.status_code == 200
    import_result = imported.json()
    assert import_result["success"] is True
    assert import_result["imported"] == 2
    assert len(import_result["imported_ids"]) == 2
    assert _count(session_factory, Goldfinger) == 2
    assert _count(session_factory, GoldfingerHistoryEvent) == 2

    listed = client.get(f"/api/goldfingers/project/{PROJECT_ID}")
    assert listed.status_code == 200
    items = {item["name"]: item for item in listed.json()["items"]}
    assert items["星火戒指"]["source"] == "imported"
    assert items["星火戒指"]["owner_character_name"] == "林墨"
    assert items["洞察之眼"]["owner_character_id"] is None
    assert items["洞察之眼"]["owner_character_name"] == "未知旅人"

    with session_factory() as session:
        source_types = list(session.execute(sa.select(GoldfingerHistoryEvent.source_type)).scalars().all())
    assert source_types == ["import", "import"]


def test_goldfinger_project_scoping_rejects_other_user_project(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_project(session_factory)
    with session_factory() as session:
        other = Goldfinger(
            id="gf-other-user",
            project_id=OTHER_PROJECT_ID,
            name="他人系统",
            normalized_name="他人系统",
            status="active",
            source="manual",
        )
        session.add(other)
        session.commit()

    assert client.get(f"/api/goldfingers/project/{OTHER_PROJECT_ID}").status_code == 404
    assert client.post(f"/api/goldfingers/project/{OTHER_PROJECT_ID}", json={"name": "越权系统"}).status_code == 404
    assert client.get("/api/goldfingers/gf-other-user").status_code == 404
    assert _count(session_factory, Goldfinger) == 1
