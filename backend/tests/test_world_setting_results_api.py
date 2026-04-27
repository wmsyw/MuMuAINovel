from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
import asyncio
from datetime import datetime, timedelta
import sys
import types
from types import SimpleNamespace
from typing import Protocol, TypeVar, cast

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.middleware import auth_middleware
from app.models import Project, WorldSettingResult
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


USER_ID = "user-world-api"
PROJECT_ID = "project-world-api"


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
        return SimpleNamespace(id=user_id, username="world-user", trust_level=1, is_admin=False)

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


def _add_world_results(session: Session) -> None:
    accepted_at = datetime(2026, 4, 27, 8, 0, 0)
    session.add(
        Project(
            id=PROJECT_ID,
            user_id=USER_ID,
            title="世界观结果 API",
            world_time_period="旧纪元三百年",
            world_location="旧都群岛",
            world_atmosphere="潮湿阴郁",
            world_rules="月潮决定灵能强弱",
        )
    )
    session.add(Project(id="project-world-other", user_id="user-other", title="其他世界"))
    session.add_all(
        [
            WorldSettingResult(
                id="world-legacy-api",
                project_id=PROJECT_ID,
                status="accepted",
                world_time_period="旧纪元三百年",
                world_location="旧都群岛",
                world_atmosphere="潮湿阴郁",
                world_rules="月潮决定灵能强弱",
                raw_result={"source": "legacy"},
                source_type="legacy_existing_record",
                accepted_at=accepted_at,
                accepted_by=USER_ID,
            ),
            WorldSettingResult(
                id="world-pending-api",
                project_id=PROJECT_ID,
                status="pending",
                world_time_period="新纪元元年",
                world_location="群星裂谷",
                world_atmosphere="壮阔紧张",
                world_rules="星核契约会反噬说谎者",
                provider="openai",
                model="gpt-5-mini",
                reasoning_intensity="high",
                raw_result={"candidate": "world-v2"},
                source_type="ai",
            ),
            WorldSettingResult(
                id="world-reject-api",
                project_id=PROJECT_ID,
                status="pending",
                world_time_period="被拒绝纪元",
                world_location="雾城",
                world_atmosphere="压抑",
                world_rules="禁用星术",
                raw_result={"candidate": "reject"},
                source_type="ai",
            ),
            WorldSettingResult(
                id="world-other-api",
                project_id="project-world-other",
                status="pending",
                world_time_period="他人项目",
                source_type="ai",
            ),
        ]
    )


def _seed_world_results(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _add_world_results(session)
        session.commit()


async def _seed_world_results_async(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.run_sync(_add_world_results)
        await session.commit()


def _project_world(session_factory: sessionmaker[Session]) -> tuple[str | None, str | None, str | None, str | None]:
    with session_factory() as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        return (project.world_time_period, project.world_location, project.world_atmosphere, project.world_rules)


def test_world_result_router_is_registered_and_lists_stable_json(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_world_results(session_factory)

    registered_paths = {route.path for route in app.routes}
    assert "/api/world-setting-results" in registered_paths
    assert "/api/world-setting-results/{result_id}/rollback" in registered_paths

    listed = client.get("/api/world-setting-results", params={"project_id": PROJECT_ID, "status": "pending"})
    fetched = client.get("/api/world-setting-results/world-pending-api")
    forbidden = client.get("/api/world-setting-results/world-other-api")

    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 2
    assert {item["id"] for item in payload["items"]} == {"world-pending-api", "world-reject-api"}
    assert {"id", "project_id", "status", "world_time_period", "provider", "model", "raw_result", "source_type"}.issubset(payload["items"][0])
    assert fetched.status_code == 200
    assert fetched.json()["id"] == "world-pending-api"
    assert fetched.json()["world_location"] == "群星裂谷"
    assert forbidden.status_code == 404


def test_accept_world_result_updates_active_snapshot_and_supersedes_previous(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_world_results(session_factory)

    response = client.post("/api/world-setting-results/world-pending-api/accept")

    assert response.status_code == 200
    payload = response.json()
    assert payload["changed"] is True
    assert payload["result"]["id"] == "world-pending-api"
    assert payload["result"]["status"] == "accepted"
    assert payload["result"]["accepted_by"] == USER_ID
    assert payload["result"]["supersedes_result_id"] == "world-legacy-api"
    assert payload["previous_result"]["id"] == "world-legacy-api"
    assert payload["active_world"] == {
        "project_id": PROJECT_ID,
        "world_time_period": "新纪元元年",
        "world_location": "群星裂谷",
        "world_atmosphere": "壮阔紧张",
        "world_rules": "星核契约会反噬说谎者",
    }
    assert _project_world(session_factory) == ("新纪元元年", "群星裂谷", "壮阔紧张", "星核契约会反噬说谎者")


def test_reject_world_result_does_not_mutate_active_snapshot(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_world_results(session_factory)
    before = _project_world(session_factory)

    response = client.post("/api/world-setting-results/world-reject-api/reject", json={"reason": "不符合设定"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["changed"] is True
    assert payload["result"]["status"] == "rejected"
    assert payload["active_world"] == {
        "project_id": PROJECT_ID,
        "world_time_period": before[0],
        "world_location": before[1],
        "world_atmosphere": before[2],
        "world_rules": before[3],
    }
    assert _project_world(session_factory) == before


def test_rollback_world_result_restores_previous_snapshot(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_world_results(session_factory)
    accepted = client.post("/api/world-setting-results/world-pending-api/accept")
    assert accepted.status_code == 200
    with session_factory() as session:
        current = session.get(WorldSettingResult, "world-pending-api")
        legacy = session.get(WorldSettingResult, "world-legacy-api")
        assert current is not None
        assert legacy is not None
        current.accepted_at = legacy.accepted_at + timedelta(hours=1)
        session.commit()

    response = client.post("/api/world-setting-results/world-pending-api/rollback", json={"reason": "恢复旧设定"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["changed"] is True
    assert payload["result"]["status"] == "superseded"
    assert payload["previous_result"]["id"] == "world-legacy-api"
    assert payload["previous_result"]["status"] == "accepted"
    assert payload["active_world"] == {
        "project_id": PROJECT_ID,
        "world_time_period": "旧纪元三百年",
        "world_location": "旧都群岛",
        "world_atmosphere": "潮湿阴郁",
        "world_rules": "月潮决定灵能强弱",
    }
    assert _project_world(session_factory) == ("旧纪元三百年", "旧都群岛", "潮湿阴郁", "月潮决定灵能强弱")


def test_rollback_world_result_restores_linked_legacy_snapshot_without_accepted_at(
    api_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, session_factory = api_client
    _seed_world_results(session_factory)
    with session_factory() as session:
        legacy = session.get(WorldSettingResult, "world-legacy-api")
        assert legacy is not None
        legacy.accepted_at = None
        session.commit()

    accepted = client.post("/api/world-setting-results/world-pending-api/accept")
    assert accepted.status_code == 200
    assert accepted.json()["result"]["supersedes_result_id"] == "world-legacy-api"

    response = client.post("/api/world-setting-results/world-pending-api/rollback", json={"reason": "恢复旧设定"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["changed"] is True
    assert payload["result"]["status"] == "superseded"
    assert payload["previous_result"]["id"] == "world-legacy-api"
    assert payload["previous_result"]["status"] == "accepted"
    assert payload["previous_result"]["accepted_at"] is not None
    assert payload["active_world"] == {
        "project_id": PROJECT_ID,
        "world_time_period": "旧纪元三百年",
        "world_location": "旧都群岛",
        "world_atmosphere": "潮湿阴郁",
        "world_rules": "月潮决定灵能强弱",
    }
    assert _project_world(session_factory) == ("旧纪元三百年", "旧都群岛", "潮湿阴郁", "月潮决定灵能强弱")


def test_async_world_result_actions_serialize_loaded_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_user(user_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=user_id, username="world-user", trust_level=1, is_admin=False)

    async def run_scenario() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_get_db() -> AsyncIterator[AsyncSession]:
            async with session_factory() as session:
                yield session

        monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
        app.dependency_overrides[get_db] = override_get_db
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            await _seed_world_results_async(session_factory)

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                client.cookies.set("session_token", create_session_token(USER_ID, 3600))

                accepted = await client.post("/api/world-setting-results/world-pending-api/accept")
                assert accepted.status_code == 200
                accepted_payload = accepted.json()
                assert accepted_payload["result"]["updated_at"] is not None
                assert accepted_payload["previous_result"]["id"] == "world-legacy-api"
                assert accepted_payload["previous_result"]["updated_at"] is not None
                assert accepted_payload["active_world"]["world_location"] == "群星裂谷"

                rejected = await client.post("/api/world-setting-results/world-reject-api/reject", json={"reason": "不符合设定"})
                assert rejected.status_code == 200
                rejected_payload = rejected.json()
                assert rejected_payload["result"]["status"] == "rejected"
                assert rejected_payload["result"]["updated_at"] is not None
                assert rejected_payload["previous_result"] is None
                assert rejected_payload["active_world"]["world_location"] == "群星裂谷"

                async with session_factory() as session:
                    current = await session.get(WorldSettingResult, "world-pending-api")
                    legacy = await session.get(WorldSettingResult, "world-legacy-api")
                    assert current is not None
                    assert legacy is not None
                    assert legacy.accepted_at is not None
                    current.accepted_at = legacy.accepted_at + timedelta(hours=1)
                    await session.commit()

                rolled_back = await client.post("/api/world-setting-results/world-pending-api/rollback", json={"reason": "恢复旧设定"})
                assert rolled_back.status_code == 200
                rollback_payload = rolled_back.json()
                assert rollback_payload["result"]["status"] == "superseded"
                assert rollback_payload["result"]["updated_at"] is not None
                assert rollback_payload["previous_result"]["id"] == "world-legacy-api"
                assert rollback_payload["previous_result"]["status"] == "accepted"
                assert rollback_payload["previous_result"]["updated_at"] is not None
                assert rollback_payload["active_world"] == {
                    "project_id": PROJECT_ID,
                    "world_time_period": "旧纪元三百年",
                    "world_location": "旧都群岛",
                    "world_atmosphere": "潮湿阴郁",
                    "world_rules": "月潮决定灵能强弱",
                }
        finally:
            app.dependency_overrides.pop(get_db, None)
            await engine.dispose()

    asyncio.run(run_scenario())


def test_openapi_schema_generation_includes_world_result_paths(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, _ = api_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    paths = openapi["paths"]
    assert "/api/world-setting-results" in paths
    assert "/api/world-setting-results/{result_id}" in paths
    assert "/api/world-setting-results/{result_id}/accept" in paths
    assert "/api/world-setting-results/{result_id}/reject" in paths
    assert "/api/world-setting-results/{result_id}/rollback" in paths

    world_result_schema = openapi["components"]["schemas"]["WorldSettingResultResponse"]
    status_enum = world_result_schema["properties"]["status"]["enum"]
    assert status_enum == ["pending", "accepted", "rejected", "superseded"]
    assert "rolled_back" not in status_enum
