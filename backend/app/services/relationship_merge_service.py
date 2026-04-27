"""Deterministic merge boundary for canonical entity relationships."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.project import Project
from app.models.relationship import EntityRelationship, ExtractionCandidate, ExtractionRun
from app.services.chapter_fact_sync_service import (
    CHAPTER_FACT_SYNC_PIPELINE_VERSION,
    ChapterFactSyncService,
)


RELATIONSHIP_LOW_CONFIDENCE_THRESHOLD = 0.70
DESTRUCTIVE_RELATIONSHIP_STATUSES = {"broken", "ended", "past", "removed", "deleted"}


@dataclass(slots=True)
class RelationshipMergeResult:
    """Relationship merge outcome."""

    relationship: EntityRelationship | None
    candidate: ExtractionCandidate | None
    changed: bool
    reason: str | None = None
    decision: str = "applied"


class RelationshipMergeService:
    """Merge character relationship facts into EntityRelationship only.

    CharacterRelationship is intentionally not touched here.  Risky or
    conflicting facts are staged as ExtractionCandidate rows so the review flow
    can decide whether to accept/override later.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def merge_character_relationship(
        self,
        *,
        project_id: str,
        character_from_id: str,
        character_to_id: str,
        relationship_type_id: int | None = None,
        relationship_name: str | None = None,
        intimacy_level: int | None = 50,
        status: str | None = "active",
        description: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        source: str = "manual",
        source_chapter_id: str | None = None,
        evidence_excerpt: str | None = None,
        confidence: float = 1.0,
        merge_decision: str = "applied",
        direction: str = "directed",
        allow_conflict_apply: bool = False,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> RelationshipMergeResult:
        project = await self._require_project(project_id)
        await self._require_character(project_id, character_from_id)
        await self._require_character(project_id, character_to_id)
        if character_from_id == character_to_id:
            return await self._stage_candidate(
                project=project,
                reason="self_loop",
                relationship=None,
                payload=self._payload(
                    project_id=project_id,
                    character_from_id=character_from_id,
                    character_to_id=character_to_id,
                    relationship_type_id=relationship_type_id,
                    relationship_name=relationship_name,
                    intimacy_level=intimacy_level,
                    status=status,
                    description=description,
                    started_at=started_at,
                    ended_at=ended_at,
                    source=source,
                    source_chapter_id=source_chapter_id,
                    evidence_excerpt=evidence_excerpt,
                    confidence=confidence,
                    old_value=old_value,
                    new_value=new_value,
                    merge_decision="pending",
                    direction=direction,
                ),
            )

        relationship = await self._find_existing_character_relationship(project_id, character_from_id, character_to_id)
        current_value = self.relationship_snapshot(relationship) if relationship is not None else old_value
        proposed_value = new_value or {
            "relationship_type_id": relationship_type_id,
            "relationship_name": relationship_name,
            "intimacy_level": intimacy_level,
            "status": status or "active",
            "description": description,
            "started_at": started_at,
            "ended_at": ended_at,
            "source": source,
        }
        conflict_reason = self._conflict_reason(
            relationship=relationship,
            relationship_type_id=relationship_type_id,
            relationship_name=relationship_name,
            status=status,
            confidence=confidence,
            character_from_id=character_from_id,
            character_to_id=character_to_id,
            direction=direction,
        )
        if conflict_reason and not allow_conflict_apply:
            return await self._stage_candidate(
                project=project,
                reason=conflict_reason,
                relationship=relationship,
                payload=self._payload(
                    project_id=project_id,
                    character_from_id=character_from_id,
                    character_to_id=character_to_id,
                    relationship_type_id=relationship_type_id,
                    relationship_name=relationship_name,
                    intimacy_level=intimacy_level,
                    status=status,
                    description=description,
                    started_at=started_at,
                    ended_at=ended_at,
                    source=source,
                    source_chapter_id=source_chapter_id,
                    evidence_excerpt=evidence_excerpt,
                    confidence=confidence,
                    old_value=current_value,
                    new_value=proposed_value,
                    merge_decision="pending",
                    direction=direction,
                ),
            )

        if relationship is None:
            relationship = EntityRelationship(
                id=str(uuid.uuid4()),
                project_id=project_id,
                from_entity_type="character",
                from_entity_id=character_from_id,
                to_entity_type="character",
                to_entity_id=character_to_id,
                relationship_type_id=relationship_type_id,
                relationship_name=relationship_name,
                intimacy_level=self._clamp_intimacy(intimacy_level),
                status=status or "active",
                description=description,
                started_at=started_at,
                ended_at=ended_at,
                source=source,
            )
            self.db.add(relationship)
            await self.db.flush()
            return RelationshipMergeResult(relationship=relationship, candidate=None, changed=True, decision=merge_decision)

        changed = False
        updates = {
            "relationship_type_id": relationship_type_id,
            "relationship_name": relationship_name,
            "intimacy_level": self._clamp_intimacy(intimacy_level),
            "status": status or relationship.status or "active",
            "description": description,
            "started_at": started_at,
            "ended_at": ended_at,
            "source": source or relationship.source,
        }
        for field, value in updates.items():
            if value is not None and getattr(relationship, field) != value:
                setattr(relationship, field, value)
                changed = True
        if changed:
            await self.db.flush()
        return RelationshipMergeResult(relationship=relationship, candidate=None, changed=changed, decision=merge_decision)

    async def _find_existing_character_relationship(
        self,
        project_id: str,
        character_from_id: str,
        character_to_id: str,
    ) -> EntityRelationship | None:
        result = await self.db.execute(
            select(EntityRelationship).where(
                EntityRelationship.project_id == project_id,
                EntityRelationship.from_entity_type == "character",
                EntityRelationship.to_entity_type == "character",
                or_(
                    and_(
                        EntityRelationship.from_entity_id == character_from_id,
                        EntityRelationship.to_entity_id == character_to_id,
                    ),
                    and_(
                        EntityRelationship.from_entity_id == character_to_id,
                        EntityRelationship.to_entity_id == character_from_id,
                    ),
                ),
            )
        )
        return result.scalars().first()

    def _conflict_reason(
        self,
        *,
        relationship: EntityRelationship | None,
        relationship_type_id: int | None,
        relationship_name: str | None,
        status: str | None,
        confidence: float,
        character_from_id: str,
        character_to_id: str,
        direction: str,
    ) -> str | None:
        if confidence < RELATIONSHIP_LOW_CONFIDENCE_THRESHOLD:
            return "low_confidence"
        if relationship is None:
            return None
        if direction == "directed" and (
            relationship.from_entity_id != character_from_id or relationship.to_entity_id != character_to_id
        ):
            return "direction_conflict"
        if relationship_type_id is not None and relationship.relationship_type_id not in (None, relationship_type_id):
            return "relationship_type_conflict"
        if relationship_name and relationship.relationship_name and relationship.relationship_name != relationship_name:
            return "relationship_name_conflict"
        if (status or "").lower() in DESTRUCTIVE_RELATIONSHIP_STATUSES and confidence < 0.92:
            return "destructive_change_requires_review"
        return None

    async def _stage_candidate(
        self,
        *,
        project: Project,
        reason: str,
        relationship: EntityRelationship | None,
        payload: dict[str, Any],
    ) -> RelationshipMergeResult:
        run = await self._get_or_create_review_run(project, payload)
        candidate = ExtractionCandidate(
            id=str(uuid.uuid4()),
            run_id=run.id,
            project_id=project.id,
            user_id=str(project.user_id or "relationship_merge_service"),
            source_chapter_id=payload.get("source_chapter_id"),
            source_chapter_start_id=payload.get("source_chapter_id"),
            source_chapter_end_id=payload.get("source_chapter_id"),
            candidate_type="relationship",
            trigger_type=str(payload.get("source") or "relationship_merge"),
            source_hash=self._source_hash(payload),
            display_name=payload.get("relationship_name") or "relationship",
            normalized_name=self._normalize(payload.get("relationship_name") or "relationship"),
            canonical_target_type="relationship" if relationship is not None else None,
            canonical_target_id=relationship.id if relationship is not None else None,
            status="pending",
            confidence=float(payload.get("confidence") or 0.0),
            evidence_text=str(payload.get("evidence_excerpt") or payload.get("description") or "relationship merge candidate"),
            source_start_offset=0,
            source_end_offset=len(str(payload.get("evidence_excerpt") or payload.get("description") or "")),
            source_chapter_order=1,
            valid_from_chapter_id=payload.get("source_chapter_id"),
            valid_from_chapter_order=1,
            story_time_label=payload.get("started_at"),
            payload=payload,
            raw_payload=payload,
            review_required_reason=reason,
        )
        self.db.add(candidate)
        await self.db.flush()
        return RelationshipMergeResult(relationship=relationship, candidate=candidate, changed=False, reason=reason, decision="pending")

    async def _get_or_create_review_run(self, project: Project, payload: dict[str, Any]) -> ExtractionRun:
        entity_type = "relationship"
        chapter_id = payload.get("source_chapter_id")
        content_hash = self._source_hash({"relationship_review_payload": payload})
        idempotency_key = ChapterFactSyncService.build_idempotency_key(
            str(chapter_id or "manual"),
            content_hash,
            "relationship-merge-service-v1",
            entity_type,
        )
        result = await self.db.execute(
            select(ExtractionRun).where(
                ExtractionRun.project_id == project.id,
                ExtractionRun.chapter_id == chapter_id,
                ExtractionRun.pipeline_version == CHAPTER_FACT_SYNC_PIPELINE_VERSION,
                ExtractionRun.schema_version == "chapter-fact-sync-review-v1:relationship",
                ExtractionRun.prompt_hash == idempotency_key,
                ExtractionRun.content_hash == content_hash,
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            return existing

        run = ExtractionRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            chapter_id=chapter_id,
            trigger_source=str(payload.get("source") or "relationship_merge"),
            pipeline_version=CHAPTER_FACT_SYNC_PIPELINE_VERSION,
            schema_version="chapter-fact-sync-review-v1:relationship",
            prompt_hash=idempotency_key,
            content_hash=content_hash,
            status="pending",
            run_metadata={
                "idempotency_key": idempotency_key,
                "entity_type": entity_type,
                "extractor_version": "relationship-merge-service-v1",
                "pipeline_version": CHAPTER_FACT_SYNC_PIPELINE_VERSION,
                "schema_version": "chapter-fact-sync-review-v1:relationship",
                "trigger_source": str(payload.get("source") or "relationship_merge"),
                "source_metadata": {"relationship_merge_pending": True},
            },
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def _require_project(self, project_id: str) -> Project:
        project = await self.db.get(Project, project_id)
        if project is None:
            raise ValueError(f"project not found: {project_id}")
        return project

    async def _require_character(self, project_id: str, character_id: str) -> Character:
        character = await self.db.get(Character, character_id)
        if character is None or character.project_id != project_id:
            raise ValueError(f"character not found in project: {character_id}")
        return character

    @staticmethod
    def relationship_snapshot(relationship: EntityRelationship | None) -> dict[str, Any] | None:
        if relationship is None:
            return None
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
        }

    def _payload(self, **values: Any) -> dict[str, Any]:
        values["from_entity_type"] = "character"
        values["from_entity_id"] = values.get("character_from_id")
        values["to_entity_type"] = "character"
        values["to_entity_id"] = values.get("character_to_id")
        values["merge_recorded_at"] = datetime.now(UTC).isoformat()
        return self._json_safe(values)

    @staticmethod
    def _clamp_intimacy(value: int | None) -> int:
        return max(-100, min(100, int(value if value is not None else 50)))

    @staticmethod
    def _json_safe(value: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    @staticmethod
    def _source_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())
