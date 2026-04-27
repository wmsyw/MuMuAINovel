from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from datetime import datetime
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
from app.models import (
    Character,
    Chapter,
    EntityProvenance,
    EntityRelationship,
    ExtractionCandidate,
    ExtractionRun,
    Goldfinger,
    GoldfingerHistoryEvent,
    Project,
    RelationshipTimelineEvent,
)
from app.security import create_session_token
from app.services.chapter_fact_sync_service import (
    CHAPTER_FACT_SYNC_EXTRACTOR_VERSION,
    CHAPTER_FACT_SYNC_PIPELINE_VERSION,
    ChapterFactSyncService,
)


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


USER_ID = "user-sync-api"
PROJECT_ID = "project-sync-api"
CHAPTER_ID = "chapter-sync-api"


class AsyncSessionAdapter:
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
        return SimpleNamespace(id=user_id, username="sync-user", trust_level=1, is_admin=False)

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


def _memory_session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    return Session(bind=connection)


def _seed_project(session: Session) -> None:
    session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="同步 API"))
    session.add(Project(id="project-sync-other", user_id="user-other", title="他人项目"))
    session.add(
        Chapter(
            id=CHAPTER_ID,
            project_id=PROJECT_ID,
            chapter_number=1,
            title="第一章",
            content="沈砚与林青岚互为盟友，天命系统首次苏醒。",
            sub_index=1,
            status="published",
        )
    )
    session.add_all([
        Character(id="char-shen", project_id=PROJECT_ID, name="沈砚"),
        Character(id="char-lin", project_id=PROJECT_ID, name="林青岚"),
    ])
    session.commit()


def _count(session: Session, model: type[object]) -> int:
    return int(session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one())


def _seed_api_base(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _seed_project(session)
        service = ChapterFactSyncService(session)
        relationship_run, goldfinger_run = service.schedule_for_chapter(
            project_id=PROJECT_ID,
            chapter_id=CHAPTER_ID,
            content="沈砚与林青岚互为盟友，天命系统首次苏醒。",
            source="manual_sync",
        )
        relationship = service.record_candidate(
            relationship_run.id,
            "relationship",
            {
                "relationship": "盟友",
                "from_entity_type": "character",
                "from_entity_id": "char-shen",
                "to_entity_type": "character",
                "to_entity_id": "char-lin",
                "source": {"order": 1, "offset_start": 0, "offset_end": 9},
            },
            0.93,
            "沈砚与林青岚互为盟友",
            "relationship_requires_review",
        )
        goldfinger = service.record_candidate(
            goldfinger_run.id,
            "goldfinger",
            {"name": "天命系统", "status": "active", "type": "system", "source": {"order": 1, "offset_start": 10, "offset_end": 18}},
            0.95,
            "天命系统首次苏醒",
            "goldfinger_merge_pending_task_4",
        )
        goldfinger_run.status = "failed"
        goldfinger_run.error_message = "extractor unavailable"
        goldfinger_run.completed_at = datetime(2026, 4, 27, 8, 0, 0)
        session.commit()
        assert relationship.id
        assert goldfinger.id


def test_schedule_for_chapter_is_idempotent_per_entity_type_and_content() -> None:
    session = _memory_session()
    _seed_project(session)
    service = ChapterFactSyncService(session)
    content = "沈砚与林青岚互为盟友，天命系统首次苏醒。"

    first = service.schedule_for_chapter(project_id=PROJECT_ID, chapter_id=CHAPTER_ID, content=content, source="chapter_save")
    second = service.schedule_for_chapter(project_id=PROJECT_ID, chapter_id=CHAPTER_ID, content=content, source="chapter_save")
    relationship_only = service.schedule_for_chapter(
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content=content,
        source="manual",
        entity_types=["relationship"],
    )
    session.flush()

    assert [run.id for run in second] == [run.id for run in first]
    assert relationship_only[0].id == first[0].id
    assert _count(session, ExtractionRun) == 2
    assert {run.status for run in first} == {"pending"}
    assert {run.run_metadata["entity_type"] for run in first} == {"relationship", "goldfinger"}
    assert all(run.run_metadata["idempotency_key"] == run.prompt_hash for run in first)
    assert ChapterFactSyncService.build_idempotency_key(
        CHAPTER_ID,
        first[0].content_hash,
        CHAPTER_FACT_SYNC_EXTRACTOR_VERSION,
        "relationship",
    ) == ChapterFactSyncService.build_idempotency_key(
        CHAPTER_ID,
        first[0].content_hash,
        CHAPTER_FACT_SYNC_EXTRACTOR_VERSION,
        "relationship",
    )


def test_process_retry_and_record_candidate_preserve_review_metadata() -> None:
    session = _memory_session()
    _seed_project(session)
    service = ChapterFactSyncService(session)
    run = service.schedule_for_chapter(
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content="沈砚与林青岚互为盟友，天命系统首次苏醒。",
        source="manual_sync",
        entity_types=["relationship"],
    )[0]

    failed = service.process_run(run.id, processor=lambda _: (_ for _ in ()).throw(RuntimeError("temporary extractor failure")))
    assert failed.status == "failed"
    assert "temporary extractor failure" in str(failed.error_message)

    retried = service.retry_run(run.id)
    assert retried.status == "pending"
    assert retried.error_message is None
    assert retried.run_metadata["retry_count"] == 1
    assert retried.run_metadata["retry_history"][0]["previous_error_message"] == "temporary extractor failure"

    candidate = service.record_candidate(
        run.id,
        "relationship",
        {"relationship": "盟友", "source": {"order": 1, "offset_start": 0, "offset_end": 9}},
        0.88,
        "沈砚与林青岚互为盟友",
        "low_confidence_manual_review",
    )
    assert candidate.status == "pending"
    assert candidate.user_id == USER_ID
    assert candidate.review_required_reason == "low_confidence_manual_review"
    assert candidate.evidence_text == "沈砚与林青岚互为盟友"


def test_sync_api_lists_retries_approves_and_rejects_candidates(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_api_base(session_factory)

    registered_paths = {route.path for route in app.routes}
    assert "/api/sync/project/{project_id}/runs" in registered_paths
    assert "/api/sync/project/{project_id}/candidates" in registered_paths
    assert "/api/sync/runs/{run_id}/retry" in registered_paths
    assert "/api/sync/candidates/{candidate_id}/approve" in registered_paths
    assert "/api/sync/candidates/{candidate_id}/reject" in registered_paths

    runs = client.get(f"/api/sync/project/{PROJECT_ID}/runs")
    assert runs.status_code == 200
    run_payload = runs.json()
    assert run_payload["total"] == 2
    failed_run = next(run for run in run_payload["items"] if run["status"] == "failed")

    retried = client.post(f"/api/sync/runs/{failed_run['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "pending"
    assert retried.json()["run_metadata"]["retry_count"] == 1
    assert retried.json()["run_metadata"]["last_error_message"] == "extractor unavailable"

    candidates = client.get(f"/api/sync/project/{PROJECT_ID}/candidates")
    assert candidates.status_code == 200
    candidate_payload = candidates.json()
    assert candidate_payload["total"] == 2
    by_type = {candidate["candidate_type"]: candidate for candidate in candidate_payload["items"]}
    assert by_type["relationship"]["review_required_reason"] == "relationship_requires_review"
    assert by_type["goldfinger"]["review_required_reason"] == "goldfinger_merge_pending_task_4"

    approve = client.post(f"/api/sync/candidates/{by_type['relationship']['id']}/approve", json={})
    assert approve.status_code == 200
    assert approve.json()["changed"] is True
    assert approve.json()["candidate"]["status"] == "merged"

    approved_goldfinger = client.post(f"/api/sync/candidates/{by_type['goldfinger']['id']}/approve", json={})
    assert approved_goldfinger.status_code == 200
    assert approved_goldfinger.json()["changed"] is True
    assert approved_goldfinger.json()["candidate"]["status"] == "accepted"

    rejected = client.post(f"/api/sync/candidates/{by_type['goldfinger']['id']}/reject", json={"reason": "误判为金手指"})
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "sync_candidate_not_pending"

    with session_factory() as session:
        replacement = ChapterFactSyncService(session).record_candidate(
            by_type["relationship"]["run_id"],
            "goldfinger",
            {"name": "误判系统", "status": "unknown"},
            0.8,
            "误判系统只是玩笑",
            "manual_review_required",
        ).id
        session.commit()

    rejected = client.post(f"/api/sync/candidates/{replacement}/reject", json={"reason": "误判为金手指"})
    assert rejected.status_code == 200
    assert rejected.json()["candidate"]["status"] == "rejected"
    assert rejected.json()["candidate"]["rejection_reason"] == "误判为金手指"

    default_after_review = client.get(f"/api/sync/project/{PROJECT_ID}/candidates")
    assert default_after_review.status_code == 200
    assert default_after_review.json() == {"total": 0, "items": []}

    explicit_rejected = client.get(f"/api/sync/project/{PROJECT_ID}/candidates", params={"status": "rejected"})
    assert explicit_rejected.status_code == 200
    assert explicit_rejected.json()["total"] == 1
    assert explicit_rejected.json()["items"][0]["id"] == replacement

    with session_factory() as session:
        assert _count(session, EntityRelationship) == 1
        assert _count(session, EntityProvenance) == 2
        assert _count(session, RelationshipTimelineEvent) == 1
        assert _count(session, Goldfinger) == 1
        assert _count(session, GoldfingerHistoryEvent) == 1
        goldfinger_candidate = session.get(ExtractionCandidate, replacement)
        assert goldfinger_candidate is not None
        assert goldfinger_candidate.rejection_reason == "误判为金手指"


def test_sync_api_project_scope_rejects_other_user_project(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_api_base(session_factory)

    with session_factory() as session:
        other_run = ExtractionRun(
            id="run-other-sync",
            project_id="project-sync-other",
            chapter_id=None,
            trigger_source="manual",
            pipeline_version=CHAPTER_FACT_SYNC_PIPELINE_VERSION,
            schema_version="chapter-fact-sync-review-v1:relationship",
            prompt_hash="other-key",
            content_hash="other-content",
            status="pending",
        )
        session.add(other_run)
        session.commit()

    assert client.get("/api/sync/project/project-sync-other/runs").status_code == 404
    assert client.post("/api/sync/runs/run-other-sync/retry").status_code == 404
