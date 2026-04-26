"""Compatibility helpers for extraction-first entity APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.relationship import EntityAlias, EntityProvenance, ExtractionCandidate, RelationshipTimelineEvent
from app.services.entity_generation_policy_service import EntityType, entity_generation_policy_service


def safe_json_loads(value: Any, default: Any = None) -> Any:
    """Parse legacy JSON text without making malformed historical values fatal."""
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return __import__("json").loads(value)
    except Exception:
        return default


def normalized_name(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


async def build_optional_entity_enrichment(
    *,
    db: AsyncSession,
    request: Request,
    project_id: str,
    entity_type: EntityType,
    entity_id: str,
    include_provenance: bool = False,
    include_aliases: bool = False,
    include_candidate_counts: bool = False,
    include_timeline: bool = False,
    include_policy_status: bool = False,
) -> dict[str, Any]:
    """Return explicit opt-in metadata without changing legacy default shapes."""

    enrichment: dict[str, Any] = {}
    if include_aliases:
        alias_rows = (
            await db.execute(
                select(EntityAlias)
                .where(
                    EntityAlias.project_id == project_id,
                    EntityAlias.entity_type == entity_type,
                    EntityAlias.entity_id == entity_id,
                    EntityAlias.status == "active",
                )
                .order_by(EntityAlias.created_at.asc(), EntityAlias.alias.asc())
            )
        ).scalars().all()
        enrichment["aliases"] = [
            {
                "id": row.id,
                "alias": row.alias,
                "normalized_alias": row.normalized_alias,
                "source": row.source,
                "status": row.status,
                "provenance_id": row.provenance_id,
            }
            for row in alias_rows
        ]

    if include_provenance:
        provenance_rows = (
            await db.execute(
                select(EntityProvenance)
                .where(
                    EntityProvenance.project_id == project_id,
                    EntityProvenance.entity_type == entity_type,
                    EntityProvenance.entity_id == entity_id,
                )
                .order_by(EntityProvenance.created_at.desc(), EntityProvenance.id.desc())
                .limit(20)
            )
        ).scalars().all()
        enrichment["provenance"] = [
            {
                "id": row.id,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "run_id": row.run_id,
                "candidate_id": row.candidate_id,
                "chapter_id": row.chapter_id,
                "claim_type": row.claim_type,
                "claim_payload": row.claim_payload,
                "evidence_text": row.evidence_text,
                "confidence": row.confidence,
                "status": row.status,
                "created_by": row.created_by,
                "created_at": _iso(row.created_at),
            }
            for row in provenance_rows
        ]

    if include_candidate_counts:
        rows = (
            await db.execute(
                select(ExtractionCandidate.status, func.count(ExtractionCandidate.id))
                .where(
                    ExtractionCandidate.project_id == project_id,
                    ExtractionCandidate.canonical_target_type == entity_type,
                    ExtractionCandidate.canonical_target_id == entity_id,
                )
                .group_by(ExtractionCandidate.status)
            )
        ).all()
        counts = {str(status): int(count) for status, count in rows}
        enrichment["candidate_counts"] = counts
        enrichment["candidate_count"] = sum(counts.values())

    if include_timeline:
        enrichment["timeline_summary"] = await _timeline_summary(
            db=db,
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if include_policy_status:
        user_id = getattr(request.state, "user_id", None)
        decision = await entity_generation_policy_service.evaluate_for_user(
            db,
            actor_user_id=user_id,
            project_id=project_id,
            entity_type=entity_type,
            source_endpoint="api.entity_compat.enrichment",
            action_type="ai_generation",
            is_admin=bool(getattr(request.state, "is_admin", False)),
            reason="实体 API 兼容响应策略状态查询",
        )
        enrichment["policy_status"] = decision.to_response()

    return enrichment


async def _timeline_summary(*, db: AsyncSession, project_id: str, entity_type: str, entity_id: str) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(RelationshipTimelineEvent)
            .where(
                RelationshipTimelineEvent.project_id == project_id,
                RelationshipTimelineEvent.event_status != "rolled_back",
            )
            .order_by(RelationshipTimelineEvent.created_at.desc(), RelationshipTimelineEvent.id.desc())
        )
    ).scalars().all()
    related = [row for row in rows if _event_mentions(row, entity_type, entity_id)]
    by_type: dict[str, int] = {}
    active = 0
    for row in related:
        by_type[row.event_type] = by_type.get(row.event_type, 0) + 1
        if row.event_status == "active":
            active += 1
    return {
        "total_events": len(related),
        "active_events": active,
        "event_type_counts": by_type,
        "latest_events": [_timeline_event_preview(row) for row in related[:5]],
    }


def _event_mentions(row: RelationshipTimelineEvent, entity_type: str, entity_id: str) -> bool:
    if entity_type == "character":
        return row.character_id == entity_id or row.related_character_id == entity_id
    if entity_type == "organization":
        return row.organization_entity_id == entity_id
    if entity_type == "career":
        return row.career_id == entity_id
    return False


def _timeline_event_preview(row: RelationshipTimelineEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "event_status": row.event_status,
        "relationship_name": row.relationship_name,
        "position": row.position,
        "career_id": row.career_id,
        "career_stage": row.career_stage,
        "valid_from_chapter_id": row.valid_from_chapter_id,
        "valid_from_chapter_order": row.valid_from_chapter_order,
        "valid_to_chapter_id": row.valid_to_chapter_id,
        "valid_to_chapter_order": row.valid_to_chapter_order,
        "confidence": row.confidence,
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def candidate_policy_payload(policy_response: dict[str, Any]) -> dict[str, Any]:
    """Stable blocked-generation payload shared by SSE endpoints."""
    return {
        **policy_response,
        "canonical_creation_allowed": bool(policy_response.get("allowed")),
        "canonical_created": False,
        "candidate_only": policy_response.get("mode") == "candidate_only",
        "candidate_review_required": policy_response.get("mode") == "candidate_only",
        "candidates": [],
    }
