from pathlib import Path
import asyncio
from collections.abc import Sequence
from typing import Protocol, TypeVar, cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Career, Character, EntityProvenance, Organization, OrganizationEntity, Project, Settings
from app.services.book_import_service import BookImportService
from app.services.entity_generation_policy_service import (
    POLICY_OVERRIDE_SOURCE_TYPE,
    ActionType,
    EntityGenerationPolicyInput,
    EntityType,
    entity_generation_policy_service,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ScalarT = TypeVar("ScalarT", covariant=True)


class ScalarResultProtocol(Protocol[ScalarT]):
    def all(self) -> Sequence[ScalarT]: ...


class ExecuteResultProtocol(Protocol):
    def scalars(self) -> ScalarResultProtocol[object]: ...
    def scalar_one(self) -> int: ...
    def scalar_one_or_none(self) -> object | None: ...
    def fetchall(self) -> Sequence[object]: ...
    def all(self) -> Sequence[object]: ...


class AsyncSessionAdapter:
    """Tiny async facade over a sync Session for focused async service tests."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return cast(ExecuteResultProtocol, self.session.execute(*args, **kwargs))

    def add(self, instance: object) -> None:
        self.session.add(instance)

    def add_all(self, instances: list[object]) -> None:
        self.session.add_all(instances)

    async def flush(self) -> None:
        self.session.flush()


def _count(session: Session, model: type[object]) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def _seed_project_and_settings(session: Session, *, allow_ai_entity_generation: bool = False) -> Project:
    project = Project(id="project-policy", user_id="user-policy", title="星门纪事")
    settings = Settings(
        id="settings-policy",
        user_id="user-policy",
        api_provider="openai",
        llm_model="gpt-5-mini",
        allow_ai_entity_generation=allow_ai_entity_generation,
    )
    session.add_all([project, settings])
    session.flush()
    return project


def _policy_input(
    *,
    allow_ai_entity_generation: bool,
    is_admin: bool = False,
    entity_type: EntityType = "character",
    action_type: ActionType = "ai_generation",
    source_endpoint: str = "tests.entity_generation_policy",
    reason: str = "focused policy test",
) -> EntityGenerationPolicyInput:
    return EntityGenerationPolicyInput(
        actor_user_id="user-policy",
        project_id="project-policy",
        entity_type=entity_type,
        source_endpoint=source_endpoint,
        action_type=action_type,
        is_admin=is_admin,
        allow_ai_entity_generation=allow_ai_entity_generation,
        provider="openai",
        model="gpt-5-mini",
        reason=reason,
    )


def test_ordinary_user_ai_generation_creates_no_canonical_entity() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_project_and_settings(session, allow_ai_entity_generation=False)
            allow_flag = entity_generation_policy_service.get_allow_ai_entity_generation_sync(session, "user-policy")
            decision = entity_generation_policy_service.evaluate(
                _policy_input(allow_ai_entity_generation=allow_flag)
            )

            if decision.allowed:
                session.add(Character(project_id="project-policy", name="不应入库"))
                session.add(OrganizationEntity(project_id="project-policy", name="不应入库组织", normalized_name="不应入库组织"))
                session.add(Career(project_id="project-policy", name="不应入库职业", type="main", stages="[]", max_stage=1))
                session.flush()

            assert decision.allowed is False
            assert decision.mode == "candidate_only"
            assert decision.code == "ai_entity_generation_disabled"
            assert _count(session, Character) == 0
            assert _count(session, OrganizationEntity) == 0
            assert _count(session, Career) == 0
            assert session.execute(
                sa.select(EntityProvenance).where(EntityProvenance.source_type == POLICY_OVERRIDE_SOURCE_TYPE)
            ).scalars().all() == []


def test_admin_override_generates_and_records_audit() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_project_and_settings(session, allow_ai_entity_generation=False)
            decision = entity_generation_policy_service.evaluate(
                _policy_input(
                    allow_ai_entity_generation=False,
                    is_admin=True,
                    entity_type="character",
                    source_endpoint="api.characters.generate_character_stream",
                    reason="admin smoke override",
                )
            )
            character = Character(id="char-admin", project_id="project-policy", name="林青岚")
            session.add(character)
            session.flush()
            audit_rows = entity_generation_policy_service.record_override_audit(session, decision, [character.id])
            session.flush()

            assert decision.allowed is True
            assert decision.override_source == "admin"
            assert _count(session, Character) == 1
            assert len(audit_rows) == 1
            audit = audit_rows[0]
            assert audit.source_type == POLICY_OVERRIDE_SOURCE_TYPE
            assert audit.created_by == "user-policy"
            assert audit.entity_type == "character"
            assert audit.entity_id == character.id
            assert audit.claim_payload["actor_user_id"] == "user-policy"
            assert audit.claim_payload["project_id"] == "project-policy"
            assert audit.claim_payload["source_endpoint"] == "api.characters.generate_character_stream"
            assert audit.claim_payload["provider"] == "openai"
            assert audit.claim_payload["model"] == "gpt-5-mini"
            assert audit.claim_payload["reason"] == "admin smoke override"
            assert audit.claim_payload["resulting_canonical_ids"] == [character.id]


def test_advanced_setting_override_generates_and_records_audit() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_project_and_settings(session, allow_ai_entity_generation=True)
            allow_flag = entity_generation_policy_service.get_allow_ai_entity_generation_sync(session, "user-policy")
            decision = entity_generation_policy_service.evaluate(
                _policy_input(
                    allow_ai_entity_generation=allow_flag,
                    entity_type="organization",
                    source_endpoint="services.auto_organization_service.check_and_create_missing_organizations",
                    reason="advanced setting smoke override",
                )
            )
            organization = OrganizationEntity(
                id="org-advanced",
                project_id="project-policy",
                name="巡星司",
                normalized_name="巡星司",
                source="ai",
            )
            session.add(organization)
            session.flush()
            audit_rows = entity_generation_policy_service.record_override_audit(session, decision, [organization.id])
            session.flush()

            assert decision.allowed is True
            assert decision.override_source == "advanced_setting"
            assert _count(session, OrganizationEntity) == 1
            assert len(audit_rows) == 1
            assert audit_rows[0].entity_type == "organization"
            assert audit_rows[0].entity_id == organization.id
            assert audit_rows[0].claim_payload["override_source"] == "advanced_setting"
            assert audit_rows[0].claim_payload["resulting_canonical_ids"] == [organization.id]


def test_manual_create_edit_allowed_without_override() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_project_and_settings(session, allow_ai_entity_generation=False)
            create_decision = entity_generation_policy_service.evaluate(
                _policy_input(allow_ai_entity_generation=False, action_type="manual_create")
            )
            edit_decision = entity_generation_policy_service.evaluate(
                _policy_input(allow_ai_entity_generation=False, action_type="manual_edit")
            )
            session.add(Character(id="char-manual", project_id="project-policy", name="手动角色"))
            session.add(Career(id="career-manual", project_id="project-policy", name="手动职业", type="main", stages="[]", max_stage=1, source="manual"))
            session.flush()
            audit_rows = entity_generation_policy_service.record_override_audit(
                session,
                create_decision,
                ["char-manual", "career-manual"],
            )

            assert create_decision.allowed is True
            assert edit_decision.allowed is True
            assert create_decision.mode == "manual_allowed"
            assert edit_decision.mode == "manual_allowed"
            assert create_decision.audit_required is False
            assert audit_rows == []
            assert _count(session, Character) == 1
            assert _count(session, Career) == 1
            assert _count(session, EntityProvenance) == 0


def test_book_import_blocked_policy_prevents_ai_calls_and_canonical_mutation() -> None:
    async def run_case() -> None:
        engine = sa.create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(bind=engine) as sync_session:
            session = AsyncSessionAdapter(sync_session)
            project = Project(id="project-policy", user_id="user-policy", title="拆书策略测试")
            settings = Settings(
                id="settings-policy",
                user_id="user-policy",
                api_provider="openai",
                llm_model="gpt-5-mini",
                allow_ai_entity_generation=False,
            )
            sync_session.add_all([project, settings])
            await session.flush()

            service = BookImportService()

            async def fail_if_ai_service_is_built(**_: object) -> object:
                raise AssertionError("blocked book-import policy path must not build or call AI service")

            setattr(service, "_build_user_ai_service", fail_if_ai_service_is_built)

            career_count = await service._generate_career_system_from_project(
                db=session,
                user_id="user-policy",
                project=project,
            )
            entity_count = await service._generate_characters_and_organizations_from_project(
                db=session,
                user_id="user-policy",
                project=project,
                count=5,
            )

            assert career_count == 0
            assert entity_count == 0
            assert await _async_count(session, Career) == 0
            assert await _async_count(session, Character) == 0
            assert await _async_count(session, Organization) == 0
            assert await _async_count(session, OrganizationEntity) == 0
            assert await _async_count(session, EntityProvenance) == 0

        engine.dispose()

    asyncio.run(run_case())


def test_book_import_advanced_override_generates_career_and_records_audit() -> None:
    class FakeAIService:
        api_provider = "openai"
        default_model = "gpt-5-mini"

        async def call_with_json_retry(self, **_: object) -> dict[str, object]:
            return {
                "main_careers": [
                    {
                        "name": "星轨师",
                        "description": "读取星轨的职业",
                        "category": "法术系",
                        "stages": [{"level": 1, "name": "初窥", "description": "初识星轨"}],
                        "max_stage": 1,
                    }
                ],
                "sub_careers": [],
            }

    async def run_case() -> None:
        engine = sa.create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(bind=engine) as sync_session:
            session = AsyncSessionAdapter(sync_session)
            project = Project(id="project-policy", user_id="user-policy", title="拆书策略测试")
            settings = Settings(
                id="settings-policy",
                user_id="user-policy",
                api_provider="openai",
                llm_model="gpt-5-mini",
                allow_ai_entity_generation=True,
            )
            sync_session.add_all([project, settings])
            await session.flush()

            service = BookImportService()

            async def fake_ai_service(**_: object) -> FakeAIService:
                return FakeAIService()

            setattr(service, "_build_user_ai_service", fake_ai_service)

            created = await service._generate_career_system_from_project(
                db=session,
                user_id="user-policy",
                project=project,
            )
            await session.flush()
            audits = cast(Sequence[EntityProvenance], (
                await session.execute(
                    sa.select(EntityProvenance).where(EntityProvenance.source_type == POLICY_OVERRIDE_SOURCE_TYPE)
                )
            ).scalars().all())
            careers = cast(Sequence[Career], (await session.execute(sa.select(Career))).scalars().all())

            assert created == 1
            assert [career.name for career in careers] == ["星轨师"]
            assert len(audits) == 1
            audit = audits[0]
            assert audit.entity_type == "career"
            assert audit.entity_id == careers[0].id
            assert audit.claim_payload["source_endpoint"] == "services.book_import_service._generate_career_system_from_project"
            assert audit.claim_payload["override_source"] == "advanced_setting"
            assert audit.claim_payload["actor_user_id"] == "user-policy"
            assert audit.claim_payload["provider"] == "openai"
            assert audit.claim_payload["model"] == "gpt-5-mini"
            assert audit.claim_payload["resulting_canonical_ids"] == [careers[0].id]

        engine.dispose()

    asyncio.run(run_case())


async def _async_count(session: AsyncSessionAdapter, model: type[object]) -> int:
    result = await session.execute(sa.select(sa.func.count()).select_from(model))
    return result.scalar_one()


def test_known_ai_generation_call_sites_use_central_policy_service() -> None:
    required_markers = {
        "app/api/characters.py": ["entity_generation_policy_service.evaluate_for_user", "record_override_audit"],
        "app/api/organizations.py": ["entity_generation_policy_service.evaluate_for_user", "record_override_audit"],
        "app/api/careers.py": ["entity_generation_policy_service.evaluate_for_user", "record_override_audit"],
        "app/api/wizard_stream.py": ["entity_generation_policy_service.evaluate_for_user", "record_override_audit", "data['is_admin']"],
        "app/api/outlines.py": ["is_admin=bool(data.get(\"is_admin\", False))", "check_and_create_missing_characters", "check_and_create_missing_organizations"],
        "app/services/auto_character_service.py": ["entity_generation_policy_service.evaluate_for_user", "record_override_audit"],
        "app/services/auto_organization_service.py": ["entity_generation_policy_service.evaluate_for_user", "record_override_audit"],
        "app/services/career_service.py": ["EntityGenerationPolicyInput", "record_override_audit"],
        "app/services/book_import_service.py": [
            "entity_generation_policy_service.evaluate_for_user",
            "services.book_import_service._generate_career_system_from_project",
            "services.book_import_service._generate_characters_and_organizations_from_project",
            "record_override_audit",
        ],
    }

    for relative_path, markers in required_markers.items():
        source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in source, f"{relative_path} missing policy marker {marker!r}"
