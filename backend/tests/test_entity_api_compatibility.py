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
from app.models import (
    Career,
    Character,
    EntityAlias,
    EntityProvenance,
    ExtractionCandidate,
    ExtractionRun,
    OrganizationEntity,
    Project,
    RelationshipTimelineEvent,
)
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

from app.api import careers, characters, organizations
from app.main import app


USER_ID = "user-entity-api"
PROJECT_ID = "project-entity-api"


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


class FakeAIService:
    api_provider = "openai"
    default_model = "gpt-5-mini"


async def fake_user_ai_service() -> FakeAIService:
    return FakeAIService()


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
        return SimpleNamespace(id=user_id, username="entity-user", trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator[AsyncSessionAdapter]:
        with session_factory() as session:
            yield AsyncSessionAdapter(session)

    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[characters.get_user_ai_service] = fake_user_ai_service
    app.dependency_overrides[organizations.get_user_ai_service] = fake_user_ai_service
    app.dependency_overrides[careers.get_user_ai_service] = fake_user_ai_service

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", create_session_token(USER_ID, 3600))
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(characters.get_user_ai_service, None)
        app.dependency_overrides.pop(organizations.get_user_ai_service, None)
        app.dependency_overrides.pop(careers.get_user_ai_service, None)
        engine.dispose()


def _seed_project(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="实体兼容"))
        session.add(
            ExtractionRun(
                id="run-entity-api",
                project_id=PROJECT_ID,
                trigger_source="manual",
                pipeline_version="test",
                schema_version="test",
                prompt_hash="prompt",
                content_hash="content",
                status="completed",
            )
        )
        session.commit()


def _count(session_factory: sessionmaker[Session], model: type[object]) -> int:
    with session_factory() as session:
        return int(session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one())


def test_legacy_character_organization_and_career_crud_shapes(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_project(session_factory)

    character = client.post("/api/characters", json={"project_id": PROJECT_ID, "name": "林青岚", "role_type": "protagonist"})
    organization = client.post(
        "/api/characters",
        json={
            "project_id": PROJECT_ID,
            "name": "巡星司",
            "is_organization": True,
            "organization_type": "官署",
            "power_level": 80,
        },
    )
    career = client.post(
        "/api/careers",
        json={
            "project_id": PROJECT_ID,
            "name": "剑修",
            "type": "main",
            "stages": [{"level": 1, "name": "初阶"}],
            "max_stage": 1,
        },
    )

    assert character.status_code == 200
    assert organization.status_code == 200
    assert career.status_code == 200
    char_payload = character.json()
    org_payload = organization.json()
    assert char_payload["is_organization"] is False
    assert org_payload["is_organization"] is True
    assert org_payload["organization_type"] == "官署"
    assert "aliases" not in char_payload
    assert "timeline_summary" not in char_payload

    listed = client.get(f"/api/characters/project/{PROJECT_ID}")
    assert listed.status_code == 200
    list_payload = listed.json()
    assert list_payload["total"] == 2
    assert {item["name"] for item in list_payload["items"]} == {"林青岚", "巡星司"}
    listed_org_id = next(item["id"] for item in list_payload["items"] if item["is_organization"])

    exported = client.post("/api/characters/export", json={"character_ids": [listed_org_id]})
    assert exported.status_code == 200
    export_payload = exported.json()
    assert export_payload["version"]
    assert export_payload["export_type"] == "characters"
    assert export_payload["count"] == 1
    assert export_payload["data"][0] == {
        **export_payload["data"][0],
        "name": "巡星司",
        "is_organization": True,
        "organization_type": "官署",
        "power_level": 80,
    }

    orgs = client.get(f"/api/organizations/project/{PROJECT_ID}")
    assert orgs.status_code == 200
    org_detail = orgs.json()[0]
    assert org_detail["name"] == "巡星司"
    assert org_detail["type"] == "官署"
    assert org_detail["member_count"] == 0

    updated_org = client.put(f"/api/organizations/{org_detail['id']}", json={"location": "天枢城", "power_level": 90})
    assert updated_org.status_code == 200
    assert updated_org.json()["location"] == "天枢城"

    member = client.post(f"/api/organizations/{org_detail['id']}/members", json={"character_id": char_payload["id"], "position": "外勤"})
    assert member.status_code == 200
    assert member.json()["organization_id"] == org_detail["id"]
    assert client.get(f"/api/organizations/{org_detail['id']}/members").json()[0]["character_name"] == "林青岚"

    career_id = career.json()["id"]
    career_list = client.get("/api/careers", params={"project_id": PROJECT_ID})
    assert career_list.status_code == 200
    assert career_list.json()["main_careers"][0]["name"] == "剑修"
    assert client.put(f"/api/careers/{career_id}", json={"description": "御剑而行"}).json()["description"] == "御剑而行"
    assert client.delete(f"/api/careers/{career_id}").status_code == 200


def test_explicit_enrichment_flags_add_metadata_without_default_shape(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_project(session_factory)
    char_id = client.post("/api/characters", json={"project_id": PROJECT_ID, "name": "沈砚"}).json()["id"]
    org_id = client.post("/api/characters", json={"project_id": PROJECT_ID, "name": "星图会", "is_organization": True}).json()["id"]
    career_id = client.post(
        "/api/careers",
        json={"project_id": PROJECT_ID, "name": "星术师", "type": "main", "stages": [{"level": 1, "name": "窥星"}], "max_stage": 1},
    ).json()["id"]

    with session_factory() as session:
        session.add_all([
            EntityAlias(project_id=PROJECT_ID, entity_type="character", entity_id=char_id, alias="沈先生", normalized_alias="沈先生", source="manual"),
            EntityAlias(project_id=PROJECT_ID, entity_type="organization", entity_id=org_id, alias="图会", normalized_alias="图会", source="manual"),
            EntityProvenance(project_id=PROJECT_ID, entity_type="character", entity_id=char_id, source_type="extraction_candidate", claim_type="character_claim", confidence=0.9),
            EntityProvenance(project_id=PROJECT_ID, entity_type="organization", entity_id=org_id, source_type="extraction_candidate", claim_type="organization_claim", confidence=0.88),
            ExtractionCandidate(id="candidate-char", run_id="run-entity-api", project_id=PROJECT_ID, user_id=USER_ID, candidate_type="character", trigger_type="manual", source_hash="hash", display_name="沈砚", normalized_name="沈砚", canonical_target_type="character", canonical_target_id=char_id, status="pending", confidence=0.9, evidence_text="沈砚", source_start_offset=0, source_end_offset=2, payload={}),
            ExtractionCandidate(id="candidate-org", run_id="run-entity-api", project_id=PROJECT_ID, user_id=USER_ID, candidate_type="organization", trigger_type="manual", source_hash="hash-org", display_name="星图会", normalized_name="星图会", canonical_target_type="organization", canonical_target_id=org_id, status="pending", confidence=0.88, evidence_text="星图会", source_start_offset=0, source_end_offset=3, payload={}),
            RelationshipTimelineEvent(project_id=PROJECT_ID, event_type="profession", event_status="active", character_id=char_id, career_id=career_id, career_stage=1),
            RelationshipTimelineEvent(project_id=PROJECT_ID, event_type="affiliation", event_status="active", organization_entity_id=org_id, character_id=char_id, position="顾问"),
        ])
        session.commit()

    default_payload = client.get(f"/api/characters/{char_id}").json()
    assert "aliases" not in default_payload
    assert "provenance" not in default_payload

    enriched = client.get(
        f"/api/characters/{char_id}",
        params={"include_aliases": True, "include_provenance": True, "include_candidate_counts": True, "include_timeline": True, "include_policy_status": True},
    ).json()
    assert enriched["aliases"][0]["alias"] == "沈先生"
    assert enriched["candidate_counts"] == {"pending": 1}
    assert enriched["timeline_summary"]["event_type_counts"]["profession"] == 1
    assert enriched["policy_status"]["mode"] == "candidate_only"

    org_enriched = client.get(f"/api/organizations/project/{PROJECT_ID}", params={"include_policy_status": True, "include_timeline": True}).json()
    assert any(item["organization_entity_id"] == org_id and item["policy_status"]["entity_type"] == "organization" for item in org_enriched)
    org_bridge_id = next(item["id"] for item in org_enriched if item["organization_entity_id"] == org_id)
    org_default = client.get(f"/api/organizations/{org_bridge_id}").json()
    assert "aliases" not in org_default
    assert "provenance" not in org_default
    org_detail = client.get(f"/api/organizations/{org_bridge_id}", params={"include_aliases": True, "include_candidate_counts": True}).json()
    assert org_detail["aliases"][0]["alias"] == "图会"
    assert org_detail["candidate_counts"] == {"pending": 1}
    career_enriched = client.get(f"/api/careers/{career_id}", params={"include_timeline": True, "include_policy_status": True}).json()
    assert career_enriched["timeline_summary"]["total_events"] == 1
    assert career_enriched["policy_status"]["entity_type"] == "career"


def test_generation_policy_blocks_ordinary_entity_endpoints_without_canonical_rows(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_project(session_factory)

    before = (_count(session_factory, Character), _count(session_factory, OrganizationEntity), _count(session_factory, Career))
    character_stream = client.post("/api/characters/generate-stream", json={"project_id": PROJECT_ID, "name": "不应入库"})
    organization_stream = client.post("/api/organizations/generate-stream", json={"project_id": PROJECT_ID, "name": "不应入库组织"})
    career_stream = client.get("/api/careers/generate-system", params={"project_id": PROJECT_ID})
    after = (_count(session_factory, Character), _count(session_factory, OrganizationEntity), _count(session_factory, Career))

    assert before == after == (0, 0, 0)
    for response in (character_stream, organization_stream, career_stream):
        assert response.status_code == 200
        assert "ai_entity_generation_disabled" in response.text
        assert "candidate_only" in response.text
        assert "canonical_created" in response.text
