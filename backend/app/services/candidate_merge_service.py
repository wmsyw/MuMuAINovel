"""Canonical candidate merge, rollback, and timeline mutation service."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import json
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.career import Career, CharacterCareer
from app.models.character import Character
from app.models.chapter import Chapter
from app.models.relationship import (
    EntityAlias,
    EntityProvenance,
    EntityRelationship,
    ExtractionCandidate,
    OrganizationEntity,
    OrganizationMember,
    RelationshipTimelineEvent,
)


EXTRACTION_SOURCE_TYPE = "extraction_candidate"
MERGE_CREATED_BY = "candidate_merge_service"
SAFE_AUTO_MERGE_CONFIDENCE = 0.92


@dataclass(slots=True)
class MergeResult:
    """Outcome for merge operations that may intentionally keep a row pending."""

    candidate: ExtractionCandidate
    changed: bool
    reason: str | None = None


class CandidateMergeService:
    """Promotes reviewed extraction candidates into provenance-aware canon."""

    def __init__(self, db: Session) -> None:
        self.db: Session = db

    def accept_candidate(
        self,
        candidate_id: str,
        *,
        reviewer_user_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        override: bool = False,
        supersedes_candidate_id: str | None = None,
    ) -> MergeResult:
        """Accept or merge a pending candidate without erasing its payload/history."""

        candidate = self._require_candidate(candidate_id)
        if candidate.status in {"accepted", "merged"}:
            return MergeResult(candidate=candidate, changed=False, reason="already accepted")
        if candidate.status in {"rejected", "superseded"}:
            return MergeResult(candidate=candidate, changed=False, reason=f"candidate is {candidate.status}")

        if candidate.candidate_type in {"character", "organization", "profession"}:
            result = self._accept_entity_candidate(
                candidate,
                reviewer_user_id=reviewer_user_id,
                target_type=target_type,
                target_id=target_id,
                override=override,
            )
        elif candidate.candidate_type == "relationship":
            result = self._accept_relationship_candidate(candidate, reviewer_user_id=reviewer_user_id, override=override)
        elif candidate.candidate_type == "organization_affiliation":
            result = self._accept_affiliation_candidate(candidate, reviewer_user_id=reviewer_user_id, override=override)
        elif candidate.candidate_type == "profession_assignment":
            result = self._accept_profession_assignment(candidate, reviewer_user_id=reviewer_user_id, override=override)
        else:
            return MergeResult(candidate=candidate, changed=False, reason="candidate type is not canonicalized by Task 7")

        if result.changed and supersedes_candidate_id:
            superseded = self.db.get(ExtractionCandidate, supersedes_candidate_id)
            if superseded is not None and superseded.id != candidate.id:
                superseded.status = "superseded"
                superseded.reviewed_at = superseded.reviewed_at or self._now()
                candidate.supersedes_candidate_id = superseded.id
        self.db.flush()
        return result

    def merge_candidate(
        self,
        candidate_id: str,
        *,
        target_type: str,
        target_id: str,
        reviewer_user_id: str | None = None,
        override: bool = False,
    ) -> MergeResult:
        """Explicitly merge a candidate into an existing canonical target."""

        return self.accept_candidate(
            candidate_id,
            reviewer_user_id=reviewer_user_id,
            target_type=target_type,
            target_id=target_id,
            override=override,
        )

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        reviewer_user_id: str | None = None,
        reason: str | None = None,
    ) -> MergeResult:
        """Reject a pending candidate idempotently without canonical mutation."""

        candidate = self._require_candidate(candidate_id)
        if candidate.status == "rejected":
            return MergeResult(candidate=candidate, changed=False, reason="already rejected")
        if candidate.status in {"accepted", "merged", "superseded"}:
            return MergeResult(candidate=candidate, changed=False, reason=f"candidate is {candidate.status}")
        candidate.status = "rejected"
        candidate.reviewer_user_id = reviewer_user_id
        candidate.reviewed_at = self._now()
        candidate.rejection_reason = reason
        self.db.flush()
        return MergeResult(candidate=candidate, changed=True)

    def rollback_candidate(
        self,
        candidate_id: str,
        *,
        reviewer_user_id: str | None = None,
        reason: str | None = None,
    ) -> MergeResult:
        """Rollback accepted candidate side effects by superseding rows, never deleting."""

        candidate = self._require_candidate(candidate_id)
        if candidate.status == "superseded":
            return MergeResult(candidate=candidate, changed=False, reason="already rolled back")
        if candidate.status not in {"accepted", "merged"}:
            return MergeResult(candidate=candidate, changed=False, reason=f"candidate is {candidate.status}")

        provenance_rows = self.db.execute(
            select(EntityProvenance).where(EntityProvenance.candidate_id == candidate.id)
        ).scalars().all()
        provenance_ids = [row.id for row in provenance_rows]
        for provenance in provenance_rows:
            provenance.status = "rolled_back"

        if provenance_ids:
            aliases = self.db.execute(
                select(EntityAlias).where(EntityAlias.provenance_id.in_(provenance_ids))
            ).scalars().all()
            for alias in aliases:
                alias.status = "retired"

            events = self.db.execute(
                select(RelationshipTimelineEvent).where(RelationshipTimelineEvent.provenance_id.in_(provenance_ids))
            ).scalars().all()
            for event in events:
                event.event_status = "rolled_back"

        candidate.status = "superseded"
        candidate.reviewer_user_id = reviewer_user_id or candidate.reviewer_user_id
        candidate.reviewed_at = candidate.reviewed_at or self._now()
        candidate.rejection_reason = reason or candidate.rejection_reason or "rolled back"
        self.db.flush()
        return MergeResult(candidate=candidate, changed=True)

    def safe_auto_merge_pending(self, *, project_id: str | None = None) -> list[MergeResult]:
        """Deterministically auto-merge only unambiguous high-confidence candidates."""

        query = select(ExtractionCandidate).where(
            ExtractionCandidate.status == "pending",
            ExtractionCandidate.confidence >= SAFE_AUTO_MERGE_CONFIDENCE,
        )
        if project_id is not None:
            query = query.where(ExtractionCandidate.project_id == project_id)

        results: list[MergeResult] = []
        for candidate in self.db.execute(query).scalars().all():
            if candidate.candidate_type not in {"character", "organization", "profession"}:
                results.append(MergeResult(candidate=candidate, changed=False, reason="safe auto-merge supports entity candidates only"))
                continue
            expected_type = self._expected_entity_type(candidate)
            names = self._candidate_names(candidate)
            matches = self._find_entity_matches(candidate.project_id, expected_type, names)
            if len(matches) != 1:
                results.append(MergeResult(candidate=candidate, changed=False, reason="safe auto-merge requires exactly one same-type match"))
                continue
            target_id = matches[0]
            results.append(
                self.merge_candidate(
                    candidate.id,
                    target_type=expected_type,
                    target_id=target_id,
                    reviewer_user_id=MERGE_CREATED_BY,
                )
            )
        return results

    def _accept_entity_candidate(
        self,
        candidate: ExtractionCandidate,
        *,
        reviewer_user_id: str | None,
        target_type: str | None,
        target_id: str | None,
        override: bool,
    ) -> MergeResult:
        expected_type = self._expected_entity_type(candidate)
        if target_type is not None and target_type != expected_type:
            return MergeResult(candidate=candidate, changed=False, reason="target type does not match candidate type")

        target = self._resolve_or_create_entity_target(
            candidate,
            expected_type=expected_type,
            target_id=target_id,
            override=override,
        )
        if target is None:
            return MergeResult(candidate=candidate, changed=False, reason="ambiguous canonical target")

        entity_id, created = target
        provenance = self._get_or_create_provenance(
            candidate=candidate,
            entity_type=expected_type,
            entity_id=entity_id,
            claim_type=f"{candidate.candidate_type}_claim",
        )
        for alias in self._candidate_alias_values(candidate):
            _ = self._get_or_create_alias(
                project_id=candidate.project_id,
                entity_type=expected_type,
                entity_id=entity_id,
                alias=alias,
                provenance_id=provenance.id,
            )

        self._mark_accepted(
            candidate,
            reviewer_user_id=reviewer_user_id,
            target_type=expected_type,
            target_id=entity_id,
            merged=not created,
        )
        return MergeResult(candidate=candidate, changed=True)

    def _accept_relationship_candidate(
        self,
        candidate: ExtractionCandidate,
        *,
        reviewer_user_id: str | None,
        override: bool,
    ) -> MergeResult:
        payload = self._payload(candidate)
        endpoints = self._relationship_endpoints(candidate, payload)
        if endpoints is None:
            return MergeResult(candidate=candidate, changed=False, reason="relationship endpoints are ambiguous or incomplete")
        from_type, from_id, to_type, to_id = endpoints
        if from_type == to_type == "character" and from_id == to_id:
            return MergeResult(candidate=candidate, changed=False, reason="relationship endpoint self-loop")

        relationship_name = self._text(payload.get("relationship") or payload.get("relationship_name") or payload.get("state") or candidate.display_name)
        if relationship_name is None:
            return MergeResult(candidate=candidate, changed=False, reason="relationship name is missing")

        relationship = self._get_or_create_entity_relationship(
            candidate=candidate,
            from_type=from_type,
            from_id=from_id,
            to_type=to_type,
            to_id=to_id,
            relationship_name=relationship_name,
            payload=payload,
        )
        ending = self._is_ending_claim(payload)
        conflict = self._active_relationship_conflict(candidate, relationship.id, relationship_name)
        if conflict is not None and not override and not ending:
            return MergeResult(candidate=candidate, changed=False, reason="conflicting active relationship claim")

        provenance = self._get_or_create_provenance(
            candidate=candidate,
            entity_type="relationship",
            entity_id=relationship.id,
            claim_type="relationship_claim",
        )
        if conflict is not None or ending:
            self._close_active_events(
                event_type="relationship",
                starts_at_candidate=candidate,
                relationship_id=relationship.id,
            )
        _ = self._get_or_create_timeline_event(
            candidate=candidate,
            provenance_id=provenance.id,
            event_type="relationship",
            event_status="ended" if ending else "active",
            relationship_id=relationship.id,
            character_id=from_id if from_type == "character" else None,
            related_character_id=to_id if to_type == "character" else None,
            organization_entity_id=from_id if from_type == "organization" else (to_id if to_type == "organization" else None),
            relationship_name=relationship_name,
        )
        self._mark_accepted(
            candidate,
            reviewer_user_id=reviewer_user_id,
            target_type="relationship",
            target_id=relationship.id,
            merged=True,
        )
        return MergeResult(candidate=candidate, changed=True)

    def _accept_affiliation_candidate(
        self,
        candidate: ExtractionCandidate,
        *,
        reviewer_user_id: str | None,
        override: bool,
    ) -> MergeResult:
        payload = self._payload(candidate)
        character_id = self._resolve_character_id(candidate.project_id, payload.get("character_id") or payload.get("character"))
        org_name = payload.get("organization") or payload.get("current_organization") or candidate.display_name
        organization_id = self._resolve_or_create_named_entity(candidate, "organization", org_name, allow_create=True)
        if character_id is None or organization_id is None:
            return MergeResult(candidate=candidate, changed=False, reason="affiliation character or organization is ambiguous")

        position = self._text(payload.get("position") or payload.get("role") or payload.get("change")) or "成员"
        rank = self._int_value(payload.get("rank"), default=0)
        conflict = self._active_affiliation_conflict(candidate, character_id, organization_id, position)
        if conflict is not None and not override:
            return MergeResult(candidate=candidate, changed=False, reason="conflicting active affiliation claim")
        if conflict is not None:
            self._close_active_events(event_type="affiliation", starts_at_candidate=candidate, character_id=character_id)

        member = self._get_or_create_organization_member(
            organization_entity_id=organization_id,
            character_id=character_id,
            position=position,
            rank=rank,
            candidate=candidate,
        )
        provenance = self._get_or_create_provenance(
            candidate=candidate,
            entity_type="organization_affiliation",
            entity_id=member.id,
            claim_type="organization_affiliation_claim",
        )
        _ = self._get_or_create_timeline_event(
            candidate=candidate,
            provenance_id=provenance.id,
            event_type="affiliation",
            organization_member_id=member.id,
            character_id=character_id,
            organization_entity_id=organization_id,
            position=position,
            rank=rank,
        )
        self._mark_accepted(
            candidate,
            reviewer_user_id=reviewer_user_id,
            target_type="organization",
            target_id=organization_id,
            merged=True,
        )
        return MergeResult(candidate=candidate, changed=True)

    def _accept_profession_assignment(
        self,
        candidate: ExtractionCandidate,
        *,
        reviewer_user_id: str | None,
        override: bool,
    ) -> MergeResult:
        payload = self._payload(candidate)
        character_id = self._resolve_character_id(candidate.project_id, payload.get("character_id") or payload.get("character"))
        career_name = payload.get("career") or payload.get("profession") or candidate.display_name
        career_id = self._resolve_or_create_named_entity(candidate, "career", career_name, allow_create=True)
        if character_id is None or career_id is None:
            return MergeResult(candidate=candidate, changed=False, reason="profession character or career is ambiguous")

        stage = self._int_value(payload.get("career_stage") or payload.get("stage"), default=1)
        conflict = self._active_profession_conflict(candidate, character_id, career_id, stage)
        if conflict is not None and not override:
            return MergeResult(candidate=candidate, changed=False, reason="conflicting active profession claim")
        if conflict is not None:
            self._close_active_events(event_type="profession", starts_at_candidate=candidate, character_id=character_id)

        assignment = self._get_or_create_character_career(character_id=character_id, career_id=career_id, stage=stage)
        provenance = self._get_or_create_provenance(
            candidate=candidate,
            entity_type="profession_assignment",
            entity_id=assignment.id,
            claim_type="profession_assignment_claim",
        )
        _ = self._get_or_create_timeline_event(
            candidate=candidate,
            provenance_id=provenance.id,
            event_type="profession",
            character_id=character_id,
            career_id=career_id,
            career_stage=stage,
        )
        self._mark_accepted(
            candidate,
            reviewer_user_id=reviewer_user_id,
            target_type="career",
            target_id=career_id,
            merged=True,
        )
        return MergeResult(candidate=candidate, changed=True)

    def _resolve_or_create_entity_target(
        self,
        candidate: ExtractionCandidate,
        *,
        expected_type: str,
        target_id: str | None,
        override: bool,
    ) -> tuple[str, bool] | None:
        if target_id is not None:
            if not self._entity_exists(candidate.project_id, expected_type, target_id):
                return None
            return target_id, False

        names = self._candidate_names(candidate)
        matches = self._find_entity_matches(candidate.project_id, expected_type, names)
        if len(matches) > 1 and not override:
            return None
        if matches:
            return matches[0], False

        entity_id = self._create_entity(candidate, expected_type)
        return entity_id, True

    def _resolve_or_create_named_entity(
        self,
        candidate: ExtractionCandidate,
        entity_type: str,
        value: Any,
        *,
        allow_create: bool,
    ) -> str | None:
        name = self._text(value)
        if name is None:
            return None
        matches = self._find_entity_matches(candidate.project_id, entity_type, {self._normalize(name)})
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1 or not allow_create:
            return None
        temp = ExtractionCandidate(
            id=candidate.id,
            project_id=candidate.project_id,
            display_name=name,
            normalized_name=self._normalize(name),
            candidate_type="organization" if entity_type == "organization" else "profession",
            payload={"display_name": name},
        )
        return self._create_entity(temp, entity_type)

    def _create_entity(self, candidate: ExtractionCandidate, entity_type: str) -> str:
        payload = self._payload(candidate)
        name = self._text(candidate.display_name or payload.get("name") or payload.get("profession") or payload.get("organization"))
        if name is None:
            name = candidate.normalized_name or "未命名"
        if entity_type == "character":
            entity = Character(
                id=str(uuid.uuid4()),
                project_id=candidate.project_id,
                name=name,
                age=self._text(payload.get("age")),
                gender=self._text(payload.get("gender")),
                role_type=self._text(payload.get("role_type")),
                personality=self._text(payload.get("personality")),
                background=self._text(payload.get("background")),
                appearance=self._text(payload.get("appearance")),
                status=self._text(payload.get("status")) or "active",
                current_state=self._text(payload.get("current_state")),
                traits=self._json_text(payload.get("traits")),
            )
        elif entity_type == "organization":
            entity = OrganizationEntity(
                id=str(uuid.uuid4()),
                project_id=candidate.project_id,
                name=name,
                normalized_name=self._normalize(name),
                personality=self._text(payload.get("personality")),
                background=self._text(payload.get("background")),
                current_state=self._text(payload.get("current_state")),
                traits=self._json_text(payload.get("traits")),
                organization_type=self._text(payload.get("organization_type")),
                organization_purpose=self._text(payload.get("organization_purpose")),
                status=self._text(payload.get("status")) or "active",
                source="ai",
            )
        elif entity_type == "career":
            entity = Career(
                id=str(uuid.uuid4()),
                project_id=candidate.project_id,
                name=name,
                type=self._text(payload.get("type")) or "main",
                description=self._text(payload.get("description")),
                category=self._text(payload.get("category")),
                stages=self._json_text(payload.get("stages")) or "[]",
                max_stage=self._int_value(payload.get("max_stage"), default=10),
                requirements=self._text(payload.get("requirements")),
                special_abilities=self._text(payload.get("special_abilities")),
                worldview_rules=self._text(payload.get("worldview_rules")),
                source="ai",
            )
        else:
            raise ValueError(f"unsupported entity type: {entity_type}")
        self.db.add(entity)
        self.db.flush()
        return entity.id

    def _find_entity_matches(self, project_id: str, entity_type: str, normalized_names: Iterable[str]) -> list[str]:
        names = {name for name in normalized_names if name}
        if not names:
            return []
        ids: set[str] = set()
        if entity_type == "character":
            rows = self.db.execute(select(Character).where(Character.project_id == project_id)).scalars().all()
            ids.update(row.id for row in rows if self._normalize(row.name) in names)
        elif entity_type == "organization":
            rows = self.db.execute(select(OrganizationEntity).where(OrganizationEntity.project_id == project_id)).scalars().all()
            ids.update(row.id for row in rows if self._normalize(row.name) in names or self._normalize(row.normalized_name) in names)
        elif entity_type == "career":
            rows = self.db.execute(select(Career).where(Career.project_id == project_id)).scalars().all()
            ids.update(row.id for row in rows if self._normalize(row.name) in names)

        aliases = self.db.execute(
            select(EntityAlias).where(
                EntityAlias.project_id == project_id,
                EntityAlias.entity_type == entity_type,
                EntityAlias.status == "active",
                EntityAlias.normalized_alias.in_(names),
            )
        ).scalars().all()
        ids.update(alias.entity_id for alias in aliases)
        return sorted(ids)

    def _entity_exists(self, project_id: str, entity_type: str, entity_id: str) -> bool:
        if entity_type == "character":
            row = self.db.get(Character, entity_id)
        elif entity_type == "organization":
            row = self.db.get(OrganizationEntity, entity_id)
        elif entity_type == "career":
            row = self.db.get(Career, entity_id)
        else:
            return False
        return row is not None and row.project_id == project_id

    def _relationship_endpoints(self, candidate: ExtractionCandidate, payload: dict[str, Any]) -> tuple[str, str, str, str] | None:
        if payload.get("from_entity_id") and payload.get("to_entity_id"):
            from_type = self._text(payload.get("from_entity_type")) or "character"
            to_type = self._text(payload.get("to_entity_type")) or "character"
            if self._entity_exists(candidate.project_id, from_type, str(payload["from_entity_id"])) and self._entity_exists(candidate.project_id, to_type, str(payload["to_entity_id"])):
                return from_type, str(payload["from_entity_id"]), to_type, str(payload["to_entity_id"])

        participants = payload.get("participants")
        if isinstance(participants, list) and len(participants) >= 2:
            left = self._resolve_endpoint(candidate.project_id, participants[0])
            right = self._resolve_endpoint(candidate.project_id, participants[1])
            if left is not None and right is not None:
                return left[0], left[1], right[0], right[1]

        left_value = payload.get("from_character") or payload.get("character") or payload.get("source_character")
        right_value = payload.get("to_character") or payload.get("related_character") or payload.get("target_character")
        left = self._resolve_endpoint(candidate.project_id, left_value)
        right = self._resolve_endpoint(candidate.project_id, right_value)
        if left is None or right is None:
            return None
        return left[0], left[1], right[0], right[1]

    def _resolve_endpoint(self, project_id: str, value: Any) -> tuple[str, str] | None:
        if isinstance(value, dict):
            entity_type = self._text(value.get("entity_type") or value.get("type")) or "character"
            entity_id = self._text(value.get("entity_id") or value.get("id"))
            if entity_id is not None and self._entity_exists(project_id, entity_type, entity_id):
                return entity_type, entity_id
            name = value.get("name") or value.get("display_name")
        else:
            entity_type = "character"
            name = value
        text = self._text(name)
        if text is None:
            return None
        matches = self._find_entity_matches(project_id, entity_type, {self._normalize(text)})
        return (entity_type, matches[0]) if len(matches) == 1 else None

    def _resolve_character_id(self, project_id: str, value: Any) -> str | None:
        if isinstance(value, str) and self._entity_exists(project_id, "character", value):
            return value
        endpoint = self._resolve_endpoint(project_id, value)
        if endpoint is None or endpoint[0] != "character":
            return None
        return endpoint[1]

    def _get_or_create_entity_relationship(
        self,
        *,
        candidate: ExtractionCandidate,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        relationship_name: str,
        payload: dict[str, Any],
    ) -> EntityRelationship:
        existing = self.db.execute(
            select(EntityRelationship).where(
                EntityRelationship.project_id == candidate.project_id,
                or_(
                    and_(
                        EntityRelationship.from_entity_type == from_type,
                        EntityRelationship.from_entity_id == from_id,
                        EntityRelationship.to_entity_type == to_type,
                        EntityRelationship.to_entity_id == to_id,
                    ),
                    and_(
                        EntityRelationship.from_entity_type == to_type,
                        EntityRelationship.from_entity_id == to_id,
                        EntityRelationship.to_entity_type == from_type,
                        EntityRelationship.to_entity_id == from_id,
                    ),
                ),
            )
        ).scalars().first()
        if existing is not None:
            return existing
        relationship = EntityRelationship(
            id=str(uuid.uuid4()),
            project_id=candidate.project_id,
            from_entity_type=from_type,
            from_entity_id=from_id,
            to_entity_type=to_type,
            to_entity_id=to_id,
            relationship_name=relationship_name,
            intimacy_level=self._int_value(payload.get("intimacy_level"), default=50),
            status="active",
            description=candidate.evidence_text,
            started_at=candidate.story_time_label,
            source="ai",
        )
        self.db.add(relationship)
        self.db.flush()
        return relationship

    def _get_or_create_organization_member(
        self,
        *,
        organization_entity_id: str,
        character_id: str,
        position: str,
        rank: int,
        candidate: ExtractionCandidate,
    ) -> OrganizationMember:
        existing = self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_entity_id == organization_entity_id,
                OrganizationMember.character_id == character_id,
                OrganizationMember.position == position,
            )
        ).scalars().first()
        if existing is not None:
            return existing
        member = OrganizationMember(
            id=str(uuid.uuid4()),
            organization_entity_id=organization_entity_id,
            character_id=character_id,
            position=position,
            rank=rank,
            status="active",
            joined_at=candidate.story_time_label,
            source="ai",
            notes=candidate.evidence_text,
        )
        self.db.add(member)
        self.db.flush()
        return member

    def _get_or_create_character_career(self, *, character_id: str, career_id: str, stage: int) -> CharacterCareer:
        existing = self.db.execute(
            select(CharacterCareer).where(
                CharacterCareer.character_id == character_id,
                CharacterCareer.career_id == career_id,
            )
        ).scalars().first()
        if existing is not None:
            return existing
        assignment = CharacterCareer(
            id=str(uuid.uuid4()),
            character_id=character_id,
            career_id=career_id,
            career_type="main",
            current_stage=stage,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def _active_relationship_conflict(self, candidate: ExtractionCandidate, relationship_id: str, relationship_name: str) -> RelationshipTimelineEvent | None:
        for event in self._active_events_at_candidate(candidate, event_type="relationship", relationship_id=relationship_id):
            if event.relationship_name != relationship_name:
                return event
        return None

    def _active_affiliation_conflict(self, candidate: ExtractionCandidate, character_id: str, organization_id: str, position: str) -> RelationshipTimelineEvent | None:
        for event in self._active_events_at_candidate(candidate, event_type="affiliation", character_id=character_id):
            if event.organization_entity_id != organization_id or event.position != position:
                return event
        return None

    def _active_profession_conflict(self, candidate: ExtractionCandidate, character_id: str, career_id: str, stage: int) -> RelationshipTimelineEvent | None:
        for event in self._active_events_at_candidate(candidate, event_type="profession", character_id=character_id):
            if event.career_id != career_id or event.career_stage != stage:
                return event
        return None

    def _active_events_at_candidate(self, candidate: ExtractionCandidate, *, event_type: str, **filters: Any) -> list[RelationshipTimelineEvent]:
        query = select(RelationshipTimelineEvent).where(
            RelationshipTimelineEvent.project_id == candidate.project_id,
            RelationshipTimelineEvent.event_type == event_type,
            RelationshipTimelineEvent.event_status == "active",
        )
        for field, value in filters.items():
            query = query.where(getattr(RelationshipTimelineEvent, field) == value)
        rows = self.db.execute(query).scalars().all()
        return [row for row in rows if self._event_contains_candidate(row, candidate)]

    def _close_active_events(self, *, event_type: str, starts_at_candidate: ExtractionCandidate, **filters: Any) -> None:
        for event in self._active_events_at_candidate(starts_at_candidate, event_type=event_type, **filters):
            event.valid_to_chapter_id = starts_at_candidate.valid_from_chapter_id
            event.valid_to_chapter_order = starts_at_candidate.valid_from_chapter_order

    def _event_contains_candidate(self, event: RelationshipTimelineEvent, candidate: ExtractionCandidate) -> bool:
        start = self._chapter_order_pair(event.valid_from_chapter_id, event.valid_from_chapter_order, default_start=True)
        end = self._chapter_order_pair(event.valid_to_chapter_id, event.valid_to_chapter_order, default_start=False)
        point = self._chapter_order_pair(candidate.valid_from_chapter_id, candidate.valid_from_chapter_order, default_start=True)
        return start <= point and (end is None or point < end)

    def _chapter_order_pair(self, chapter_id: str | None, order: int | None, *, default_start: bool) -> tuple[int, int] | None:
        if chapter_id is None:
            return (-1_000_000, 0) if default_start else None
        chapter = self.db.get(Chapter, chapter_id)
        if chapter is None:
            return (-1_000_000, 0) if default_start else None
        return int(chapter.chapter_number), int(order if order is not None else chapter.chapter_number)

    def _get_or_create_provenance(
        self,
        *,
        candidate: ExtractionCandidate,
        entity_type: str,
        entity_id: str,
        claim_type: str,
    ) -> EntityProvenance:
        existing = self.db.execute(
            select(EntityProvenance).where(
                EntityProvenance.project_id == candidate.project_id,
                EntityProvenance.entity_type == entity_type,
                EntityProvenance.entity_id == entity_id,
                EntityProvenance.source_type == EXTRACTION_SOURCE_TYPE,
                EntityProvenance.source_id == candidate.id,
                EntityProvenance.candidate_id == candidate.id,
                EntityProvenance.claim_type == claim_type,
                EntityProvenance.status == "active",
            )
        ).scalars().first()
        if existing is not None:
            return existing
        provenance = EntityProvenance(
            id=str(uuid.uuid4()),
            project_id=candidate.project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source_type=EXTRACTION_SOURCE_TYPE,
            source_id=candidate.id,
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            chapter_id=candidate.source_chapter_id,
            claim_type=claim_type,
            claim_payload=self._payload(candidate),
            evidence_text=candidate.evidence_text,
            source_start=candidate.source_start_offset,
            source_end=candidate.source_end_offset,
            confidence=candidate.confidence,
            status="active",
            created_by=candidate.reviewer_user_id or MERGE_CREATED_BY,
        )
        self.db.add(provenance)
        self.db.flush()
        return provenance

    def _get_or_create_alias(
        self,
        *,
        project_id: str,
        entity_type: str,
        entity_id: str,
        alias: str,
        provenance_id: str,
    ) -> EntityAlias | None:
        normalized_alias = self._normalize(alias)
        if not normalized_alias:
            return None
        existing = self.db.execute(
            select(EntityAlias).where(
                EntityAlias.project_id == project_id,
                EntityAlias.entity_type == entity_type,
                EntityAlias.entity_id == entity_id,
                EntityAlias.normalized_alias == normalized_alias,
                EntityAlias.status == "active",
            )
        ).scalars().first()
        if existing is not None:
            return existing
        row = EntityAlias(
            id=str(uuid.uuid4()),
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            alias=alias.strip(),
            normalized_alias=normalized_alias,
            source=EXTRACTION_SOURCE_TYPE,
            provenance_id=provenance_id,
            status="active",
        )
        self.db.add(row)
        return row

    def _get_or_create_timeline_event(self, *, candidate: ExtractionCandidate, provenance_id: str, event_type: str, event_status: str = "active", **values: Any) -> RelationshipTimelineEvent:
        existing = self.db.execute(
            select(RelationshipTimelineEvent).where(
                RelationshipTimelineEvent.project_id == candidate.project_id,
                RelationshipTimelineEvent.event_type == event_type,
                RelationshipTimelineEvent.provenance_id == provenance_id,
            )
        ).scalars().first()
        if existing is not None:
            return existing
        self._validate_candidate_bounds(candidate)
        event = RelationshipTimelineEvent(
            id=str(uuid.uuid4()),
            project_id=candidate.project_id,
            event_type=event_type,
            event_status=event_status,
            source_chapter_id=candidate.source_chapter_id,
            source_chapter_order=candidate.source_chapter_order,
            valid_from_chapter_id=candidate.valid_from_chapter_id,
            valid_from_chapter_order=candidate.valid_from_chapter_order,
            valid_to_chapter_id=candidate.valid_to_chapter_id,
            valid_to_chapter_order=candidate.valid_to_chapter_order,
            source_start_offset=candidate.source_start_offset,
            source_end_offset=candidate.source_end_offset,
            evidence_text=candidate.evidence_text,
            confidence=candidate.confidence,
            provenance_id=provenance_id,
            story_time_label=candidate.story_time_label,
            **values,
        )
        self.db.add(event)
        return event

    def _validate_candidate_bounds(self, candidate: ExtractionCandidate) -> None:
        if candidate.valid_from_chapter_id is None or candidate.valid_to_chapter_id is None:
            return
        start = self._chapter_order_pair(candidate.valid_from_chapter_id, candidate.valid_from_chapter_order, default_start=True)
        end = self._chapter_order_pair(candidate.valid_to_chapter_id, candidate.valid_to_chapter_order, default_start=False)
        if end is not None and start >= end:
            raise ValueError("candidate valid_from must be before valid_to")

    def _mark_accepted(
        self,
        candidate: ExtractionCandidate,
        *,
        reviewer_user_id: str | None,
        target_type: str,
        target_id: str,
        merged: bool,
    ) -> None:
        now = self._now()
        candidate.status = "merged" if merged else "accepted"
        candidate.canonical_target_type = target_type if target_type in {"character", "organization", "career"} else candidate.canonical_target_type
        candidate.canonical_target_id = target_id if target_type in {"character", "organization", "career"} else candidate.canonical_target_id
        candidate.merge_target_type = target_type
        candidate.merge_target_id = target_id
        candidate.reviewer_user_id = reviewer_user_id
        candidate.reviewed_at = now
        candidate.accepted_at = candidate.accepted_at or now

    def _candidate_names(self, candidate: ExtractionCandidate) -> set[str]:
        return {self._normalize(value) for value in self._candidate_alias_values(candidate)}

    def _candidate_alias_values(self, candidate: ExtractionCandidate) -> list[str]:
        payload = self._payload(candidate)
        values: list[str] = []
        for value in (candidate.display_name, candidate.normalized_name, payload.get("name"), payload.get("profession"), payload.get("organization")):
            text = self._text(value)
            if text is not None:
                values.append(text)
        aliases = payload.get("aliases")
        if isinstance(aliases, list):
            values.extend(str(alias).strip() for alias in aliases if str(alias or "").strip())
        return list(dict.fromkeys(values))

    def _expected_entity_type(self, candidate: ExtractionCandidate) -> str:
        if candidate.candidate_type == "profession":
            return "career"
        expected = candidate.canonical_target_type or candidate.candidate_type
        if expected not in {"character", "organization", "career"}:
            raise ValueError(f"candidate has no entity target type: {candidate.candidate_type}")
        return expected

    def _payload(self, candidate: ExtractionCandidate) -> dict[str, Any]:
        return candidate.payload if isinstance(candidate.payload, dict) else {}

    def _require_candidate(self, candidate_id: str) -> ExtractionCandidate:
        candidate = self.db.get(ExtractionCandidate, candidate_id)
        if candidate is None:
            raise ValueError(f"candidate not found: {candidate_id}")
        return candidate

    def _is_ending_claim(self, payload: dict[str, Any]) -> bool:
        status = self._normalize(payload.get("status") or payload.get("state") or payload.get("change") or payload.get("relationship_status"))
        return status in {"ended", "end", "past", "broken", "结束", "终止", "决裂"}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _normalize(value: Any) -> str:
        text = str(value or "").strip().lower()
        return " ".join(text.split())

    @staticmethod
    def _text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _int_value(value: Any, *, default: int) -> int:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _json_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)


def accept_candidate(db: Session, candidate_id: str, **kwargs: Any) -> MergeResult:
    """Convenience wrapper for tests and future routers."""

    return CandidateMergeService(db).accept_candidate(candidate_id, **kwargs)


def rollback_candidate(db: Session, candidate_id: str, **kwargs: Any) -> MergeResult:
    """Convenience wrapper for tests and future routers."""

    return CandidateMergeService(db).rollback_candidate(candidate_id, **kwargs)
