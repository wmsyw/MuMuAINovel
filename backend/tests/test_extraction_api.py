from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
import sys
import types
from types import SimpleNamespace
from typing import Any, Protocol, TypeVar, cast

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.middleware import auth_middleware
from app.models import Character, Chapter, EntityProvenance, ExtractionCandidate, ExtractionRun, Project
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


USER_ID = "user-extraction-api"
PROJECT_ID = "project-extraction-api"
RUN_ID = "run-extraction-api"


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
        return SimpleNamespace(id=user_id, username="api-user", trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator["AsyncSessionAdapter"]:
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


class AsyncSessionAdapter:
    """Tiny async facade over a sync Session for FastAPI route tests."""

    def __init__(self, session: Session) -> None:
        self.session: SyncSessionProtocol = cast(SyncSessionProtocol, session)

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return self.session.execute(*args, **kwargs)

    async def run_sync(self, fn: Callable[[SyncSessionProtocol], RunSyncT]) -> RunSyncT:
        return fn(self.session)

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()


def _seed_base(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="抽取评审 API"))
        session.add(Project(id="project-other", user_id="user-other", title="其他项目"))
        session.add_all(
            [
                Chapter(
                    id="chapter-api-1",
                    project_id=PROJECT_ID,
                    chapter_number=1,
                    title="第一章",
                    content="沈砚在雨夜加入巡星司。",
                    sub_index=1,
                    status="published",
                ),
                Chapter(
                    id="chapter-api-2",
                    project_id=PROJECT_ID,
                    chapter_number=2,
                    title="第二章",
                    content="林青岚记录星图会线索。",
                    sub_index=2,
                    status="published",
                ),
            ]
        )
        session.add(
            ExtractionRun(
                id=RUN_ID,
                project_id=PROJECT_ID,
                chapter_id="chapter-api-1",
                trigger_source="manual",
                pipeline_version="test-pipeline",
                schema_version="test-schema",
                prompt_hash="prompt-hash",
                content_hash="content-hash",
                status="completed",
                provider="fake",
                model="fake-model",
                run_metadata={"source": "test"},
            )
        )
        session.add(
            ExtractionRun(
                id="run-pending",
                project_id=PROJECT_ID,
                chapter_id="chapter-api-2",
                trigger_source="manual",
                pipeline_version="test-pipeline",
                schema_version="test-schema",
                prompt_hash="prompt-hash-2",
                content_hash="content-hash-2",
                status="pending",
            )
        )
        session.add(Character(id="char-existing", project_id=PROJECT_ID, name="林青岚"))
        session.add_all(
            [
                _candidate("cand-accept", "沈砚", candidate_type="character"),
                _candidate("cand-invalid-merge", "不存在目标", candidate_type="character"),
                _candidate("cand-rollback", "顾北辰", candidate_type="character"),
                _candidate(
                    "cand-targeted",
                    "林青岚",
                    candidate_type="character",
                    canonical_target_type="character",
                    canonical_target_id="char-existing",
                ),
                _candidate("cand-rejected", "旧线索", candidate_type="world_fact", status="rejected"),
            ]
        )
        session.commit()


def _candidate(
    candidate_id: str,
    display_name: str,
    *,
    candidate_type: str,
    status: str = "pending",
    canonical_target_type: str | None = None,
    canonical_target_id: str | None = None,
) -> ExtractionCandidate:
    return ExtractionCandidate(
        id=candidate_id,
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        user_id=USER_ID,
        source_chapter_id="chapter-api-1",
        source_chapter_start_id="chapter-api-1",
        source_chapter_end_id="chapter-api-1",
        candidate_type=candidate_type,
        trigger_type="manual",
        source_hash=f"source-{candidate_id}",
        display_name=display_name,
        normalized_name=display_name,
        canonical_target_type=canonical_target_type or ({"character": "character", "organization": "organization", "profession": "career"}.get(candidate_type)),
        canonical_target_id=canonical_target_id,
        status=status,
        confidence=0.95,
        evidence_text=display_name,
        source_start_offset=0,
        source_end_offset=len(display_name),
        source_chapter_number=1,
        source_chapter_order=1,
        valid_from_chapter_id="chapter-api-1",
        valid_from_chapter_order=1,
        story_time_label="第一章",
        payload={"display_name": display_name, "name": display_name, "aliases": []},
        raw_payload={"candidate_type": candidate_type, "display_name": display_name},
    )


def _count(session_factory: sessionmaker[Session], model: type[object]) -> int:
    with session_factory() as session:
        result = session.execute(sa.select(sa.func.count()).select_from(model))
        return int(result.scalar_one())


def _candidate_status(session_factory: sessionmaker[Session], candidate_id: str) -> str:
    with session_factory() as session:
        result = session.execute(select_candidate_status(candidate_id))
        return str(result.scalar_one())


def select_candidate_status(candidate_id: str):
    return sa.select(ExtractionCandidate.status).where(ExtractionCandidate.id == candidate_id)


def test_router_is_registered_under_api_and_lists_stable_json(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_base(session_factory)

    registered_paths = {route.path for route in app.routes}
    assert "/api/extraction/runs" in registered_paths
    assert "/api/extraction/candidates/{candidate_id}/merge" in registered_paths

    runs = client.get("/api/extraction/runs", params={"project_id": PROJECT_ID, "status": "completed"})
    assert runs.status_code == 200
    run_payload = runs.json()
    assert run_payload["total"] == 1
    assert run_payload["items"][0] == {
        **run_payload["items"][0],
        "id": RUN_ID,
        "project_id": PROJECT_ID,
        "chapter_id": "chapter-api-1",
        "status": "completed",
        "trigger_source": "manual",
        "pipeline_version": "test-pipeline",
        "schema_version": "test-schema",
    }

    candidates = client.get(
        "/api/extraction/candidates",
        params={"project_id": PROJECT_ID, "status": "pending", "type": "character", "chapter_id": "chapter-api-1", "run_id": RUN_ID},
    )
    assert candidates.status_code == 200
    candidate_payload = candidates.json()
    assert candidate_payload["total"] == 4
    first = candidate_payload["items"][0]
    assert {
        "id",
        "run_id",
        "project_id",
        "candidate_type",
        "status",
        "confidence",
        "payload",
        "canonical_target_type",
        "canonical_target_id",
    }.issubset(first)

    targeted = client.get("/api/extraction/candidates", params={"project_id": PROJECT_ID, "canonical_target": "character:char-existing"})
    assert targeted.status_code == 200
    assert targeted.json()["total"] == 1
    assert targeted.json()["items"][0]["id"] == "cand-targeted"


def test_accept_candidate_success_creates_canonical_response(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_base(session_factory)

    response = client.post("/api/extraction/candidates/cand-accept/accept", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["changed"] is True
    assert payload["candidate"]["id"] == "cand-accept"
    assert payload["candidate"]["status"] == "accepted"
    assert payload["candidate"]["reviewer_user_id"] == USER_ID
    assert payload["candidate"]["canonical_target_type"] == "character"
    assert payload["candidate"]["canonical_target_id"]
    assert _count(session_factory, Character) == 2
    assert _count(session_factory, EntityProvenance) == 1


def test_invalid_merge_target_returns_structured_error_without_mutation(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_base(session_factory)
    before_characters = _count(session_factory, Character)
    before_provenance = _count(session_factory, EntityProvenance)

    response = client.post(
        "/api/extraction/candidates/cand-invalid-merge/merge",
        json={"target_type": "character", "target_id": "missing-character"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "candidate_merge_failed",
        "message": "ambiguous canonical target",
    }
    assert _count(session_factory, Character) == before_characters
    assert _count(session_factory, EntityProvenance) == before_provenance
    assert _candidate_status(session_factory, "cand-invalid-merge") == "pending"


def test_rollback_candidate_supersedes_merge_side_effects(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_base(session_factory)

    accepted = client.post("/api/extraction/candidates/cand-rollback/accept", json={})
    assert accepted.status_code == 200
    assert accepted.json()["candidate"]["status"] == "accepted"

    rolled_back = client.post("/api/extraction/candidates/cand-rollback/rollback", json={"reason": "误抽取"})

    assert rolled_back.status_code == 200
    payload = rolled_back.json()
    assert payload["changed"] is True
    assert payload["candidate"]["status"] == "superseded"
    assert payload["candidate"]["rejection_reason"] == "误抽取"
    assert _candidate_status(session_factory, "cand-rollback") == "superseded"

    def provenance_statuses() -> list[str]:
        with session_factory() as session:
            result = session.execute(sa.select(EntityProvenance.status).where(EntityProvenance.candidate_id == "cand-rollback"))
            return [str(status) for status in result.scalars().all()]

    assert provenance_statuses() == ["rolled_back"]


def test_openapi_schema_generation_includes_extraction_paths(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, _ = api_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths: dict[str, Any] = response.json()["paths"]
    assert "/api/extraction/runs" in paths
    assert "/api/extraction/runs/{run_id}" in paths
    assert "/api/extraction/candidates" in paths
    assert "/api/extraction/candidates/{candidate_id}/accept" in paths
    assert "/api/extraction/candidates/{candidate_id}/reject" in paths
    assert "/api/extraction/candidates/{candidate_id}/merge" in paths
    assert "/api/extraction/candidates/{candidate_id}/rollback" in paths
