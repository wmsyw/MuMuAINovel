import socket

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Career,
    Character,
    CharacterCareer,
    CharacterRelationship,
    EntityAlias,
    EntityProvenance,
    EntityRelationship,
    ExtractionRun,
    Organization,
    OrganizationEntity,
    OrganizationMember,
    Project,
    RelationshipTimelineEvent,
    WorldSettingResult,
)
from app.services.legacy_backfill_service import LEGACY_SOURCE_TYPE, backfill_legacy_project_canon


def _count(session: Session, model: type[object]) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def _seed_legacy_project(session: Session) -> None:
    project = Project(
        id="project-legacy",
        user_id="user-legacy",
        title="北境旧案",
        description="旧项目",
        world_time_period="灵历三百年",
        world_location="北境雪原",
        world_atmosphere="肃杀而清冷",
        world_rules="灵脉会在月圆时复苏",
    )
    protagonist = Character(
        id="char-linqinglan",
        project_id=project.id,
        name="林青岚",
        age="十九",
        gender="女",
        role_type="protagonist",
        personality="冷静",
        background="北境剑修",
        status="active",
        current_state="准备下山",
    )
    guardian = Character(
        id="char-moyan",
        project_id=project.id,
        name="墨岩",
        age="未知",
        gender="男",
        role_type="supporting",
        personality="沉稳",
        background="旧时代守门人",
        status="active",
    )
    organization = OrganizationEntity(
        id="orgentity-qinglan",
        project_id=project.id,
        name="青岚阁",
        normalized_name="青岚阁",
        personality="戒律森严",
        background="守护北境的宗门",
        status="active",
        current_state="声望上升",
        traits='["宗门"]',
        organization_type="宗门",
        organization_purpose="守护封印",
        level=2,
        power_level=88,
        member_count=300,
        location="北境雪山",
        motto="护道守心",
        color="青色",
        legacy_character_id="char-org-qinglan",
        legacy_organization_id="org-legacy-qinglan",
        source="legacy",
    )
    organization_bridge = Organization(
        id="org-legacy-qinglan",
        character_id="char-org-qinglan",
        project_id=project.id,
        organization_entity_id=organization.id,
    )
    member = OrganizationMember(
        id="member-linqinglan",
        organization_id=organization_bridge.id,
        organization_entity_id=organization.id,
        character_id=protagonist.id,
        position="阁主",
        rank=9,
        status="active",
        joined_at="第一章前",
        loyalty=95,
        contribution=80,
        source="manual",
        notes="旧资料登记的青岚阁阁主",
    )
    career = Career(
        id="career-sword",
        project_id=project.id,
        name="剑修",
        type="main",
        description="以剑入道",
        category="战斗系",
        stages='[{"level": 1, "name": "凝气"}, {"level": 2, "name": "筑基"}]',
        max_stage=9,
        requirements="剑心通明",
        special_abilities="御剑",
        worldview_rules="受灵脉影响",
        source="manual",
    )
    career_assignment = CharacterCareer(
        id="charcareer-linqinglan-sword",
        character_id=protagonist.id,
        career_id=career.id,
        career_type="main",
        current_stage=3,
        stage_progress=40,
        started_at="幼年",
        reached_current_stage_at="第一章前",
        notes="旧设定中的主修职业",
    )
    legacy_relationship = CharacterRelationship(
        id="rel-legacy-guardian",
        project_id=project.id,
        character_from_id=guardian.id,
        character_to_id=protagonist.id,
        relationship_name="守护者",
        intimacy_level=75,
        status="active",
        description="墨岩暗中守护林青岚",
        started_at="序章前",
        source="manual",
    )
    session.add_all([
        project,
        protagonist,
        guardian,
        organization,
        organization_bridge,
        member,
        career,
        career_assignment,
        legacy_relationship,
    ])
    session.flush()


def test_legacy_backfill_is_idempotent_and_preserves_existing_records(monkeypatch) -> None:
    network_attempts: list[tuple[object, object]] = []

    def fail_on_network(self, address):
        network_attempts.append((self, address))
        raise AssertionError(f"legacy backfill attempted network access: {address}")

    monkeypatch.setattr(socket.socket, "connect", fail_on_network)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_legacy_project(session)

            first = backfill_legacy_project_canon(session, "project-legacy")
            first_counts = {
                "provenance": _count(session, EntityProvenance),
                "aliases": _count(session, EntityAlias),
                "entity_relationships": _count(session, EntityRelationship),
                "timeline_events": _count(session, RelationshipTimelineEvent),
                "world_results": _count(session, WorldSettingResult),
                "extraction_runs": _count(session, ExtractionRun),
            }

            second = backfill_legacy_project_canon(session, "project-legacy")
            second_counts = {
                "provenance": _count(session, EntityProvenance),
                "aliases": _count(session, EntityAlias),
                "entity_relationships": _count(session, EntityRelationship),
                "timeline_events": _count(session, RelationshipTimelineEvent),
                "world_results": _count(session, WorldSettingResult),
                "extraction_runs": _count(session, ExtractionRun),
            }

            assert first.provenance_created == 8
            assert first.aliases_created == 4
            assert first.entity_relationships_created == 1
            assert first.timeline_events_created == 3
            assert first.world_results_created == 1
            assert second.provenance_created == 0
            assert second.aliases_created == 0
            assert second.entity_relationships_created == 0
            assert second.timeline_events_created == 0
            assert second.world_results_created == 0
            assert second_counts == first_counts
            assert first_counts == {
                "provenance": 8,
                "aliases": 4,
                "entity_relationships": 1,
                "timeline_events": 3,
                "world_results": 1,
                "extraction_runs": 0,
            }

            provenance_rows = session.execute(sa.select(EntityProvenance)).scalars().all()
            assert {row.source_type for row in provenance_rows} == {LEGACY_SOURCE_TYPE}
            assert {row.confidence for row in provenance_rows} == {1.0}
            assert {row.run_id for row in provenance_rows} == {None}
            assert {row.candidate_id for row in provenance_rows} == {None}
            assert {row.chapter_id for row in provenance_rows} == {None}

            aliases = session.execute(
                sa.select(EntityAlias.entity_type, EntityAlias.alias, EntityAlias.normalized_alias)
                .order_by(EntityAlias.entity_type, EntityAlias.alias)
            ).all()
            assert aliases == [
                ("career", "剑修", "剑修"),
                ("character", "墨岩", "墨岩"),
                ("character", "林青岚", "林青岚"),
                ("organization", "青岚阁", "青岚阁"),
            ]

            timeline_events = session.execute(sa.select(RelationshipTimelineEvent)).scalars().all()
            assert {event.event_type for event in timeline_events} == {"relationship", "affiliation", "profession"}
            assert {event.confidence for event in timeline_events} == {1.0}
            assert {event.source_chapter_id for event in timeline_events} == {None}
            assert {event.valid_from_chapter_id for event in timeline_events} == {None}
            assert {event.valid_to_chapter_id for event in timeline_events} == {None}

            relationship_event = next(event for event in timeline_events if event.event_type == "relationship")
            entity_relationship = session.execute(sa.select(EntityRelationship)).scalar_one()
            assert entity_relationship.legacy_character_relationship_id == "rel-legacy-guardian"
            assert relationship_event.relationship_id == entity_relationship.id
            assert relationship_event.relationship_name == "守护者"

            affiliation_event = next(event for event in timeline_events if event.event_type == "affiliation")
            assert affiliation_event.organization_member_id == "member-linqinglan"
            assert affiliation_event.organization_entity_id == "orgentity-qinglan"
            assert affiliation_event.position == "阁主"

            profession_event = next(event for event in timeline_events if event.event_type == "profession")
            assert profession_event.character_id == "char-linqinglan"
            assert profession_event.career_id == "career-sword"
            assert profession_event.career_stage == 3

            world_result = session.execute(sa.select(WorldSettingResult)).scalar_one()
            assert world_result.status == "accepted"
            assert world_result.source_type == LEGACY_SOURCE_TYPE
            assert world_result.run_id is None
            assert world_result.provider is None
            assert world_result.model is None
            assert world_result.accepted_by == "user-legacy"
            assert world_result.world_time_period == "灵历三百年"
            assert world_result.world_location == "北境雪原"
            assert world_result.world_atmosphere == "肃杀而清冷"
            assert world_result.world_rules == "灵脉会在月圆时复苏"

            # Original records remain queryable and editable after the backfill.
            character = session.get(Character, "char-linqinglan")
            organization = session.get(OrganizationEntity, "orgentity-qinglan")
            career = session.get(Career, "career-sword")
            member = session.get(OrganizationMember, "member-linqinglan")
            relationship = session.get(CharacterRelationship, "rel-legacy-guardian")
            assert character is not None
            assert organization is not None
            assert career is not None
            assert member is not None
            assert relationship is not None

            character.current_state = "已完成旧资料回填"
            organization.location = "北境新雪山"
            career.description = "以剑入道，兼修旧谱"
            member.notes = "仍可编辑的旧成员记录"
            relationship.description = "仍可编辑的旧关系记录"
            session.flush()

            assert session.get(Character, "char-linqinglan").current_state == "已完成旧资料回填"
            assert session.get(OrganizationEntity, "orgentity-qinglan").location == "北境新雪山"
            assert session.get(Career, "career-sword").description == "以剑入道，兼修旧谱"
            assert session.get(OrganizationMember, "member-linqinglan").notes == "仍可编辑的旧成员记录"
            assert session.get(CharacterRelationship, "rel-legacy-guardian").description == "仍可编辑的旧关系记录"

    assert network_attempts == []
