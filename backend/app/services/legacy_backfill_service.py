"""Idempotent legacy canonical provenance backfill.

This module converts already-persisted project records into the provenance-aware
canon added by the extraction graph schema.  It deliberately does not call AI,
network clients, or extraction-run code; every row it creates is derived from an
existing database record.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.career import Career, CharacterCareer
from app.models.character import Character
from app.models.project import Project
from app.models.relationship import (
    CharacterRelationship,
    EntityAlias,
    EntityProvenance,
    EntityRelationship,
    OrganizationEntity,
    OrganizationMember,
    RelationshipTimelineEvent,
    WorldSettingResult,
)


LEGACY_SOURCE_TYPE = "legacy_existing_record"
LEGACY_CREATED_BY = "legacy_backfill"


@dataclass(slots=True)
class LegacyBackfillSummary:
    """Counters for a single legacy backfill run."""

    projects_seen: int = 0
    provenance_created: int = 0
    aliases_created: int = 0
    entity_relationships_created: int = 0
    timeline_events_created: int = 0
    world_results_created: int = 0
    details: dict[str, int] = field(default_factory=dict)

    def bump(self, key: str, amount: int = 1) -> None:
        self.details[key] = self.details.get(key, 0) + amount


def backfill_legacy_project_canon(db: Session, project_id: str) -> LegacyBackfillSummary:
    """Backfill one project into provenance-compatible canonical rows."""

    return LegacyBackfillService(db).backfill_project(project_id)


def backfill_all_legacy_canon(db: Session) -> LegacyBackfillSummary:
    """Backfill every project currently present in the database."""

    return LegacyBackfillService(db).backfill_all_projects()


class LegacyBackfillService:
    """Backfills existing manual/legacy records without inference or AI calls."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.summary = LegacyBackfillSummary()

    def backfill_all_projects(self) -> LegacyBackfillSummary:
        projects = self.db.execute(select(Project.id)).scalars().all()
        for project_id in projects:
            self.backfill_project(project_id)
        self.db.flush()
        return self.summary

    def backfill_project(self, project_id: str) -> LegacyBackfillSummary:
        project = self.db.get(Project, project_id)
        if project is None:
            return self.summary

        self.summary.projects_seen += 1

        self._backfill_characters(project)
        self._backfill_organization_entities(project)
        self._backfill_careers(project)
        self._ensure_entity_relationships_from_legacy_relationships(project)
        self._backfill_entity_relationships(project)
        self._backfill_organization_memberships(project)
        self._backfill_character_careers(project)
        self._backfill_world_settings(project)

        self.db.flush()
        return self.summary

    def _backfill_characters(self, project: Project) -> None:
        characters = self.db.execute(
            select(Character).where(Character.project_id == project.id)
        ).scalars().all()
        for character in characters:
            provenance = self._get_or_create_provenance(
                project_id=project.id,
                entity_type="character",
                entity_id=character.id,
                source_id=character.id,
                claim_type="character_record",
                claim_payload=self._character_payload(character),
                evidence_text=character.name,
                created_by=project.user_id or LEGACY_CREATED_BY,
            )
            self._get_or_create_alias(
                project_id=project.id,
                entity_type="character",
                entity_id=character.id,
                alias=character.name,
                provenance_id=provenance.id,
            )

    def _backfill_organization_entities(self, project: Project) -> None:
        organizations = self.db.execute(
            select(OrganizationEntity).where(OrganizationEntity.project_id == project.id)
        ).scalars().all()
        for organization in organizations:
            provenance = self._get_or_create_provenance(
                project_id=project.id,
                entity_type="organization",
                entity_id=organization.id,
                source_id=organization.legacy_organization_id or organization.id,
                claim_type="organization_record",
                claim_payload=self._organization_payload(organization),
                evidence_text=organization.name,
                created_by=project.user_id or LEGACY_CREATED_BY,
            )
            self._get_or_create_alias(
                project_id=project.id,
                entity_type="organization",
                entity_id=organization.id,
                alias=organization.name,
                provenance_id=provenance.id,
            )

    def _backfill_careers(self, project: Project) -> None:
        careers = self.db.execute(
            select(Career).where(Career.project_id == project.id)
        ).scalars().all()
        for career in careers:
            provenance = self._get_or_create_provenance(
                project_id=project.id,
                entity_type="career",
                entity_id=career.id,
                source_id=career.id,
                claim_type="career_record",
                claim_payload=self._career_payload(career),
                evidence_text=career.name,
                created_by=project.user_id or LEGACY_CREATED_BY,
            )
            self._get_or_create_alias(
                project_id=project.id,
                entity_type="career",
                entity_id=career.id,
                alias=career.name,
                provenance_id=provenance.id,
            )

    def _ensure_entity_relationships_from_legacy_relationships(self, project: Project) -> None:
        relationships = self.db.execute(
            select(CharacterRelationship).where(CharacterRelationship.project_id == project.id)
        ).scalars().all()
        for relationship in relationships:
            existing = self.db.execute(
                select(EntityRelationship).where(
                    EntityRelationship.legacy_character_relationship_id == relationship.id
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue

            from_type, from_id = self._resolve_relationship_endpoint(relationship.character_from_id)
            to_type, to_id = self._resolve_relationship_endpoint(relationship.character_to_id)
            entity_relationship = EntityRelationship(
                id=str(uuid.uuid4()),
                project_id=project.id,
                from_entity_type=from_type,
                from_entity_id=from_id,
                to_entity_type=to_type,
                to_entity_id=to_id,
                relationship_type_id=relationship.relationship_type_id,
                relationship_name=relationship.relationship_name,
                intimacy_level=relationship.intimacy_level,
                status=relationship.status or "active",
                description=relationship.description,
                started_at=relationship.started_at,
                ended_at=relationship.ended_at,
                source=relationship.source or "legacy",
                legacy_character_relationship_id=relationship.id,
                created_at=relationship.created_at,
                updated_at=relationship.updated_at,
            )
            self.db.add(entity_relationship)
            self.summary.entity_relationships_created += 1
            self.summary.bump("entity_relationships")

    def _backfill_entity_relationships(self, project: Project) -> None:
        relationships = self.db.execute(
            select(EntityRelationship).where(EntityRelationship.project_id == project.id)
        ).scalars().all()
        for relationship in relationships:
            provenance = self._get_or_create_provenance(
                project_id=project.id,
                entity_type="relationship",
                entity_id=relationship.id,
                source_id=relationship.legacy_character_relationship_id or relationship.id,
                claim_type="relationship_record",
                claim_payload=self._relationship_payload(relationship),
                evidence_text=relationship.description or relationship.relationship_name,
                created_by=project.user_id or LEGACY_CREATED_BY,
            )
            self._get_or_create_timeline_event(
                project_id=project.id,
                event_type="relationship",
                provenance_id=provenance.id,
                relationship_id=relationship.id,
                character_id=self._character_endpoint_id(relationship.from_entity_type, relationship.from_entity_id),
                related_character_id=self._character_endpoint_id(relationship.to_entity_type, relationship.to_entity_id),
                organization_entity_id=self._organization_endpoint_id(relationship.from_entity_type, relationship.from_entity_id)
                or self._organization_endpoint_id(relationship.to_entity_type, relationship.to_entity_id),
                relationship_name=relationship.relationship_name,
                story_time_label=relationship.started_at,
                evidence_text=relationship.description or relationship.relationship_name,
            )

    def _backfill_organization_memberships(self, project: Project) -> None:
        members = self.db.execute(
            select(OrganizationMember).where(OrganizationMember.organization_entity_id.in_(
                select(OrganizationEntity.id).where(OrganizationEntity.project_id == project.id)
            ))
        ).scalars().all()
        for member in members:
            provenance = self._get_or_create_provenance(
                project_id=project.id,
                entity_type="organization_affiliation",
                entity_id=member.id,
                source_id=member.id,
                claim_type="organization_membership_record",
                claim_payload=self._organization_member_payload(member),
                evidence_text=member.notes or member.position,
                created_by=project.user_id or LEGACY_CREATED_BY,
            )
            self._get_or_create_timeline_event(
                project_id=project.id,
                event_type="affiliation",
                provenance_id=provenance.id,
                organization_member_id=member.id,
                character_id=member.character_id,
                organization_entity_id=member.organization_entity_id,
                position=member.position,
                rank=member.rank,
                story_time_label=member.joined_at,
                evidence_text=member.notes or member.position,
            )

    def _backfill_character_careers(self, project: Project) -> None:
        assignments = self.db.execute(
            select(CharacterCareer)
            .join(Character, CharacterCareer.character_id == Character.id)
            .where(Character.project_id == project.id)
        ).scalars().all()
        for assignment in assignments:
            provenance = self._get_or_create_provenance(
                project_id=project.id,
                entity_type="profession_assignment",
                entity_id=assignment.id,
                source_id=assignment.id,
                claim_type="character_career_record",
                claim_payload=self._character_career_payload(assignment),
                evidence_text=assignment.notes,
                created_by=project.user_id or LEGACY_CREATED_BY,
            )
            self._get_or_create_timeline_event(
                project_id=project.id,
                event_type="profession",
                provenance_id=provenance.id,
                character_id=assignment.character_id,
                career_id=assignment.career_id,
                career_stage=assignment.current_stage,
                story_time_label=assignment.started_at or assignment.reached_current_stage_at,
                evidence_text=assignment.notes,
            )

    def _backfill_world_settings(self, project: Project) -> None:
        if not any(_has_text(value) for value in _world_values(project)):
            return

        self._get_or_create_provenance(
            project_id=project.id,
            entity_type="world_setting",
            entity_id=project.id,
            source_id=project.id,
            claim_type="world_setting_record",
            claim_payload=self._world_payload(project),
            evidence_text=_join_text(_world_values(project)),
            created_by=project.user_id or LEGACY_CREATED_BY,
        )

        existing = self.db.execute(
            select(WorldSettingResult).where(
                WorldSettingResult.project_id == project.id,
                WorldSettingResult.run_id.is_(None),
                WorldSettingResult.status == "accepted",
                WorldSettingResult.source_type == LEGACY_SOURCE_TYPE,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return

        result = WorldSettingResult(
            id=str(uuid.uuid4()),
            project_id=project.id,
            run_id=None,
            status="accepted",
            world_time_period=project.world_time_period,
            world_location=project.world_location,
            world_atmosphere=project.world_atmosphere,
            world_rules=project.world_rules,
            prompt=None,
            provider=None,
            model=None,
            reasoning_intensity=None,
            raw_result=self._world_payload(project),
            source_type=LEGACY_SOURCE_TYPE,
            accepted_at=datetime.utcnow(),
            accepted_by=project.user_id,
        )
        self.db.add(result)
        self.summary.world_results_created += 1
        self.summary.bump("world_setting_results")

    def _get_or_create_provenance(
        self,
        *,
        project_id: str,
        entity_type: str,
        entity_id: str,
        source_id: str,
        claim_type: str,
        claim_payload: dict[str, Any],
        evidence_text: str | None,
        created_by: str,
    ) -> EntityProvenance:
        existing = self.db.execute(
            select(EntityProvenance).where(
                EntityProvenance.project_id == project_id,
                EntityProvenance.entity_type == entity_type,
                EntityProvenance.entity_id == entity_id,
                EntityProvenance.source_type == LEGACY_SOURCE_TYPE,
                EntityProvenance.source_id == source_id,
                EntityProvenance.claim_type == claim_type,
                EntityProvenance.status == "active",
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        provenance = EntityProvenance(
            id=str(uuid.uuid4()),
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source_type=LEGACY_SOURCE_TYPE,
            source_id=source_id,
            run_id=None,
            candidate_id=None,
            chapter_id=None,
            claim_type=claim_type,
            claim_payload=claim_payload,
            evidence_text=evidence_text,
            source_start=None,
            source_end=None,
            confidence=1.0,
            status="active",
            created_by=created_by,
        )
        self.db.add(provenance)
        self.db.flush()
        self.summary.provenance_created += 1
        self.summary.bump("entity_provenance")
        return provenance

    def _get_or_create_alias(
        self,
        *,
        project_id: str,
        entity_type: str,
        entity_id: str,
        alias: str | None,
        provenance_id: str,
    ) -> EntityAlias | None:
        normalized_alias = _normalize(alias)
        if not normalized_alias or alias is None:
            return None

        existing = self.db.execute(
            select(EntityAlias).where(
                EntityAlias.project_id == project_id,
                EntityAlias.entity_type == entity_type,
                EntityAlias.entity_id == entity_id,
                EntityAlias.normalized_alias == normalized_alias,
                EntityAlias.status == "active",
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        row = EntityAlias(
            id=str(uuid.uuid4()),
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            alias=alias.strip(),
            normalized_alias=normalized_alias,
            source=LEGACY_SOURCE_TYPE,
            provenance_id=provenance_id,
            status="active",
        )
        self.db.add(row)
        self.summary.aliases_created += 1
        self.summary.bump("entity_aliases")
        return row

    def _get_or_create_timeline_event(self, *, project_id: str, event_type: str, **values: Any) -> RelationshipTimelineEvent:
        query = select(RelationshipTimelineEvent).where(
            RelationshipTimelineEvent.project_id == project_id,
            RelationshipTimelineEvent.event_type == event_type,
            RelationshipTimelineEvent.event_status == "active",
            RelationshipTimelineEvent.valid_from_chapter_id.is_(None),
            RelationshipTimelineEvent.valid_to_chapter_id.is_(None),
        )
        if values.get("relationship_id") is not None:
            query = query.where(RelationshipTimelineEvent.relationship_id == values["relationship_id"])
        if values.get("organization_member_id") is not None:
            query = query.where(RelationshipTimelineEvent.organization_member_id == values["organization_member_id"])
        if values.get("career_id") is not None:
            query = query.where(
                RelationshipTimelineEvent.character_id == values.get("character_id"),
                RelationshipTimelineEvent.career_id == values["career_id"],
            )
        existing = self.db.execute(query).scalar_one_or_none()
        if existing is not None:
            return existing

        event = RelationshipTimelineEvent(
            id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=event_type,
            event_status="active",
            source_chapter_id=None,
            source_chapter_order=None,
            valid_from_chapter_id=None,
            valid_from_chapter_order=None,
            valid_to_chapter_id=None,
            valid_to_chapter_order=None,
            source_start_offset=None,
            source_end_offset=None,
            confidence=1.0,
            **values,
        )
        self.db.add(event)
        self.summary.timeline_events_created += 1
        self.summary.bump("relationship_timeline_events")
        return event

    def _resolve_relationship_endpoint(self, legacy_character_id: str) -> tuple[str, str]:
        organization = self.db.execute(
            select(OrganizationEntity).where(OrganizationEntity.legacy_character_id == legacy_character_id)
        ).scalar_one_or_none()
        if organization is not None:
            return "organization", organization.id
        return "character", legacy_character_id

    @staticmethod
    def _character_endpoint_id(entity_type: str, entity_id: str) -> str | None:
        return entity_id if entity_type == "character" else None

    @staticmethod
    def _organization_endpoint_id(entity_type: str, entity_id: str) -> str | None:
        return entity_id if entity_type == "organization" else None

    @staticmethod
    def _character_payload(character: Character) -> dict[str, Any]:
        return {
            "id": character.id,
            "name": character.name,
            "age": character.age,
            "gender": character.gender,
            "role_type": character.role_type,
            "personality": character.personality,
            "background": character.background,
            "appearance": character.appearance,
            "relationships": character.relationships,
            "status": character.status,
            "current_state": character.current_state,
            "main_career_id": character.main_career_id,
            "main_career_stage": character.main_career_stage,
            "sub_careers": character.sub_careers,
            "avatar_url": character.avatar_url,
            "traits": character.traits,
        }

    @staticmethod
    def _organization_payload(organization: OrganizationEntity) -> dict[str, Any]:
        return {
            "id": organization.id,
            "name": organization.name,
            "normalized_name": organization.normalized_name,
            "personality": organization.personality,
            "background": organization.background,
            "current_state": organization.current_state,
            "traits": organization.traits,
            "organization_type": organization.organization_type,
            "organization_purpose": organization.organization_purpose,
            "status": organization.status,
            "parent_org_id": organization.parent_org_id,
            "legacy_character_id": organization.legacy_character_id,
            "legacy_organization_id": organization.legacy_organization_id,
            "level": organization.level,
            "power_level": organization.power_level,
            "member_count": organization.member_count,
            "location": organization.location,
            "motto": organization.motto,
            "color": organization.color,
            "source": organization.source,
        }

    @staticmethod
    def _career_payload(career: Career) -> dict[str, Any]:
        return {
            "id": career.id,
            "name": career.name,
            "type": career.type,
            "description": career.description,
            "category": career.category,
            "stages": career.stages,
            "max_stage": career.max_stage,
            "requirements": career.requirements,
            "special_abilities": career.special_abilities,
            "worldview_rules": career.worldview_rules,
            "attribute_bonuses": career.attribute_bonuses,
            "source": career.source,
        }

    @staticmethod
    def _relationship_payload(relationship: EntityRelationship) -> dict[str, Any]:
        return {
            "id": relationship.id,
            "from_entity_type": relationship.from_entity_type,
            "from_entity_id": relationship.from_entity_id,
            "to_entity_type": relationship.to_entity_type,
            "to_entity_id": relationship.to_entity_id,
            "relationship_type_id": relationship.relationship_type_id,
            "relationship_name": relationship.relationship_name,
            "intimacy_level": relationship.intimacy_level,
            "status": relationship.status,
            "description": relationship.description,
            "started_at": relationship.started_at,
            "ended_at": relationship.ended_at,
            "source": relationship.source,
            "legacy_character_relationship_id": relationship.legacy_character_relationship_id,
        }

    @staticmethod
    def _organization_member_payload(member: OrganizationMember) -> dict[str, Any]:
        return {
            "id": member.id,
            "organization_id": member.organization_id,
            "organization_entity_id": member.organization_entity_id,
            "character_id": member.character_id,
            "position": member.position,
            "rank": member.rank,
            "status": member.status,
            "joined_at": member.joined_at,
            "left_at": member.left_at,
            "loyalty": member.loyalty,
            "contribution": member.contribution,
            "source": member.source,
            "notes": member.notes,
        }

    @staticmethod
    def _character_career_payload(assignment: CharacterCareer) -> dict[str, Any]:
        return {
            "id": assignment.id,
            "character_id": assignment.character_id,
            "career_id": assignment.career_id,
            "career_type": assignment.career_type,
            "current_stage": assignment.current_stage,
            "stage_progress": assignment.stage_progress,
            "started_at": assignment.started_at,
            "reached_current_stage_at": assignment.reached_current_stage_at,
            "notes": assignment.notes,
        }

    @staticmethod
    def _world_payload(project: Project) -> dict[str, Any]:
        return {
            "world_time_period": project.world_time_period,
            "world_location": project.world_location,
            "world_atmosphere": project.world_atmosphere,
            "world_rules": project.world_rules,
        }


def _normalize(value: str | None) -> str:
    return value.strip().lower() if value and value.strip() else ""


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _world_values(project: Project) -> tuple[str | None, str | None, str | None, str | None]:
    return (
        project.world_time_period,
        project.world_location,
        project.world_atmosphere,
        project.world_rules,
    )


def _join_text(values: Iterable[str | None]) -> str | None:
    text = "\n".join(value.strip() for value in values if value is not None and value.strip())
    return text or None
