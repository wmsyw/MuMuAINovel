"""Deterministic goldfinger extraction candidate sync and merge service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.goldfinger import GOLDFINGER_STATUSES, Goldfinger
from app.models.relationship import EntityProvenance, ExtractionCandidate, ExtractionRun
from app.services.chapter_fact_sync_service import ChapterFactSyncService
from app.services.goldfinger_service import GoldfingerService


GOLDFINGER_SYNC_CREATED_BY = "goldfinger_sync_service"
GOLDFINGER_AUTO_MERGE_CONFIDENCE = 0.92
GOLDFINGER_REQUIRED_CHANGE_FIELDS: tuple[str, ...] = (
    "name",
    "normalized_name",
    "owner_character_name",
    "owner_character_id",
    "type",
    "status",
    "summary",
    "rules",
    "tasks",
    "rewards",
    "limits",
    "trigger_conditions",
    "cooldown",
    "aliases",
    "operation",
    "evidence_excerpt",
    "confidence",
    "conflict_hint",
)
DESTRUCTIVE_OPERATIONS = {"delete", "remove", "lost", "seal", "sealed", "disable", "revoke", "archive"}


@dataclass(slots=True)
class GoldfingerSyncResult:
    """Outcome for a goldfinger extraction candidate decision."""

    candidate: ExtractionCandidate
    changed: bool
    reason: str | None = None
    goldfinger_id: str | None = None


class GoldfingerSyncService:
    """Merge high-confidence goldfinger facts while keeping risky claims pending."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def process_run_changes(
        self,
        run_id: str,
        changes: list[dict[str, Any]],
        *,
        auto_merge: bool = True,
    ) -> list[GoldfingerSyncResult]:
        """Record goldfinger extraction changes and auto-merge safe candidates.

        The method is idempotent for the same run/change payload: it reuses the
        existing candidate decision row and does not duplicate canonical rows,
        history events, or provenance.
        """

        run = self._require_run(run_id)
        results: list[GoldfingerSyncResult] = []
        for index, raw_change in enumerate(changes or [], start=1):
            payload = self.normalize_change(raw_change)
            payload["source_chapter_order"] = payload.get("source_chapter_order") or index
            candidate = self._get_or_record_candidate(run, payload)
            if auto_merge and candidate.status == "pending":
                results.append(self.accept_candidate(candidate.id, reviewer_user_id=GOLDFINGER_SYNC_CREATED_BY))
            else:
                results.append(GoldfingerSyncResult(candidate=candidate, changed=False, reason=f"candidate is {candidate.status}"))
        self.db.flush()
        return results

    def accept_candidate(
        self,
        candidate_id: str,
        *,
        reviewer_user_id: str | None = None,
        target_id: str | None = None,
        override: bool = False,
    ) -> GoldfingerSyncResult:
        """Accept a pending goldfinger candidate into canonical state when safe."""

        candidate = self._require_candidate(candidate_id)
        if candidate.candidate_type != "goldfinger":
            return GoldfingerSyncResult(candidate=candidate, changed=False, reason="candidate is not goldfinger")
        if candidate.status in {"accepted", "merged"}:
            return GoldfingerSyncResult(candidate=candidate, changed=False, reason="already accepted", goldfinger_id=candidate.merge_target_id)
        if candidate.status in {"rejected", "superseded"}:
            return GoldfingerSyncResult(candidate=candidate, changed=False, reason=f"candidate is {candidate.status}")

        payload = self.normalize_change(self._payload(candidate))
        candidate.payload = {**payload, "goldfinger_sync_key": self._candidate_key(candidate.run_id, payload)}
        candidate.raw_payload = candidate.raw_payload or payload

        reason = self._pending_reason(candidate, payload, target_id=target_id, override=override)
        if reason is not None:
            candidate.review_required_reason = reason
            self._set_decision(candidate, action="pending", reason=reason)
            self.db.flush()
            return GoldfingerSyncResult(candidate=candidate, changed=False, reason=reason)

        goldfinger, created = self._resolve_or_create_goldfinger(candidate, payload, target_id=target_id)
        old_snapshot = None if created else GoldfingerService.response_dict(goldfinger)
        applied_fields = self._apply_additive_fields(goldfinger, payload, allow_status_override=override)
        goldfinger.updated_by = reviewer_user_id or candidate.user_id or GOLDFINGER_SYNC_CREATED_BY
        goldfinger.confidence = max(float(goldfinger.confidence or 0.0), float(candidate.confidence or 0.0))
        goldfinger.last_source_chapter_id = candidate.source_chapter_id or goldfinger.last_source_chapter_id
        self.db.flush()

        new_snapshot = GoldfingerService.response_dict(goldfinger)
        if created or applied_fields:
            GoldfingerService.add_history_event(
                self.db,
                goldfinger=goldfinger,
                event_type="created" if created else "extraction_merge",
                old_value=old_snapshot,
                new_value=new_snapshot if created else {field: new_snapshot.get(field) for field in applied_fields},
                source_type="extraction",
                chapter_id=candidate.source_chapter_id,
                evidence_excerpt=candidate.evidence_text,
                confidence=candidate.confidence,
            )
        provenance = self._get_or_create_provenance(candidate, goldfinger.id)
        candidate.status = "accepted" if created else "merged"
        candidate.canonical_target_type = "goldfinger"
        candidate.canonical_target_id = goldfinger.id
        candidate.merge_target_type = "goldfinger"
        candidate.merge_target_id = goldfinger.id
        candidate.reviewer_user_id = reviewer_user_id
        candidate.reviewed_at = self._now()
        candidate.accepted_at = candidate.accepted_at or candidate.reviewed_at
        candidate.review_required_reason = None
        self._set_decision(
            candidate,
            action="accepted" if created else "merged",
            reason=None,
            target_id=goldfinger.id,
            applied_fields=applied_fields,
            provenance_id=provenance.id,
        )
        self.db.flush()
        return GoldfingerSyncResult(candidate=candidate, changed=True, goldfinger_id=goldfinger.id)

    @classmethod
    def normalize_change(cls, raw_change: dict[str, Any]) -> dict[str, Any]:
        """Normalize model output while preserving the Task 4 schema fields."""

        raw = dict(raw_change or {})
        name = cls._text(raw.get("name") or raw.get("goldfinger_name") or raw.get("display_name"))
        normalized_name = GoldfingerService.normalized_name(raw.get("normalized_name") or name)
        status = cls._text(raw.get("status")) or "unknown"
        if status not in GOLDFINGER_STATUSES:
            status = "unknown"
        confidence = cls._confidence(raw.get("confidence"))
        payload: dict[str, Any] = {
            "name": name,
            "normalized_name": normalized_name,
            "owner_character_name": cls._text(raw.get("owner_character_name") or raw.get("owner_name")),
            "owner_character_id": cls._text(raw.get("owner_character_id") or raw.get("owner_id")),
            "type": cls._text(raw.get("type")),
            "status": status,
            "summary": cls._text(raw.get("summary")),
            "rules": cls._jsonish(raw.get("rules")),
            "tasks": cls._listish(raw.get("tasks")),
            "rewards": cls._listish(raw.get("rewards")),
            "limits": cls._jsonish(raw.get("limits")),
            "trigger_conditions": cls._jsonish(raw.get("trigger_conditions")),
            "cooldown": cls._jsonish(raw.get("cooldown")),
            "aliases": cls._string_list(raw.get("aliases")),
            "operation": (cls._text(raw.get("operation")) or "upsert").lower(),
            "evidence_excerpt": cls._text(raw.get("evidence_excerpt") or raw.get("evidence_text")) or "",
            "confidence": confidence,
            "conflict_hint": cls._text(raw.get("conflict_hint")),
        }
        for key in ("source_start_offset", "source_end_offset", "source_chapter_order", "story_time_label"):
            if key in raw:
                payload[key] = raw[key]
        metadata_value = raw.get("metadata")
        metadata = metadata_value if isinstance(metadata_value, dict) else {}
        usage_examples = cls._listish(raw.get("usage_examples") or metadata.get("usage_examples"))
        if metadata or usage_examples:
            payload["metadata"] = {**metadata, "usage_examples": usage_examples}
        return payload

    def _pending_reason(self, candidate: ExtractionCandidate, payload: dict[str, Any], *, target_id: str | None, override: bool) -> str | None:
        if not payload.get("name") or not payload.get("normalized_name"):
            return "missing_goldfinger_name"
        if float(candidate.confidence or 0.0) < GOLDFINGER_AUTO_MERGE_CONFIDENCE and not override:
            return "low_confidence"
        if payload.get("operation") in DESTRUCTIVE_OPERATIONS and not candidate.evidence_text.strip():
            return "missing_evidence_for_destructive_operation"
        owner_reason = self._resolve_owner(candidate.project_id, payload)
        if owner_reason is not None and not override:
            return owner_reason
        target = self._resolve_target(candidate.project_id, payload, target_id=target_id, override=override)
        if target.reason is not None:
            return target.reason
        if target.goldfinger is None:
            return None
        return self._conflict_reason(target.goldfinger, payload, override=override)

    def _resolve_or_create_goldfinger(self, candidate: ExtractionCandidate, payload: dict[str, Any], *, target_id: str | None) -> tuple[Goldfinger, bool]:
        owner_id, owner_name = self._owner_snapshot(candidate.project_id, payload)
        target = self._resolve_target(candidate.project_id, payload, target_id=target_id, override=True).goldfinger
        if target is not None:
            return target, False
        goldfinger = Goldfinger(
            id=str(uuid.uuid4()),
            project_id=candidate.project_id,
            name=str(payload["name"]),
            normalized_name=str(payload["normalized_name"]),
            owner_character_id=owner_id,
            owner_character_name=owner_name,
            type=payload.get("type"),
            status=payload.get("status") or "unknown",
            summary=payload.get("summary"),
            rules=payload.get("rules"),
            tasks=payload.get("tasks"),
            rewards=payload.get("rewards"),
            limits=payload.get("limits"),
            trigger_conditions=payload.get("trigger_conditions"),
            cooldown=payload.get("cooldown"),
            aliases=payload.get("aliases"),
            goldfinger_metadata=payload.get("metadata"),
            created_by=candidate.user_id or GOLDFINGER_SYNC_CREATED_BY,
            updated_by=candidate.reviewer_user_id or candidate.user_id or GOLDFINGER_SYNC_CREATED_BY,
            source="extraction",
            confidence=candidate.confidence,
            last_source_chapter_id=candidate.source_chapter_id,
        )
        self.db.add(goldfinger)
        self.db.flush()
        return goldfinger, True

    def _apply_additive_fields(self, goldfinger: Goldfinger, payload: dict[str, Any], *, allow_status_override: bool) -> list[str]:
        changed: list[str] = []
        for field in ("owner_character_id", "owner_character_name"):
            value = self._owner_snapshot(goldfinger.project_id, payload)[0 if field.endswith("_id") else 1]
            if value and not getattr(goldfinger, field):
                setattr(goldfinger, field, value)
                changed.append(field)
        for field in ("type", "summary", "trigger_conditions", "cooldown"):
            value = payload.get(field)
            if value and not getattr(goldfinger, field):
                setattr(goldfinger, field, value)
                changed.append(field)
        if payload.get("summary") and goldfinger.summary and payload["summary"] != goldfinger.summary and goldfinger.summary in payload["summary"]:
            goldfinger.summary = payload["summary"]
            changed.append("summary")
        status = payload.get("status")
        if status and status != "unknown" and (goldfinger.status == "unknown" or allow_status_override) and goldfinger.status != status:
            goldfinger.status = status
            changed.append("status")
        for field in ("rules", "limits"):
            value = payload.get(field)
            if value and not getattr(goldfinger, field):
                setattr(goldfinger, field, value)
                changed.append(field)
        for field in ("aliases", "tasks", "rewards"):
            merged = self._merge_json_list(getattr(goldfinger, field), payload.get(field))
            if merged != (getattr(goldfinger, field) or []):
                setattr(goldfinger, field, merged)
                changed.append(field)
        metadata = self._merge_metadata(goldfinger.goldfinger_metadata, payload.get("metadata"))
        if metadata != (goldfinger.goldfinger_metadata or {}):
            goldfinger.goldfinger_metadata = metadata
            changed.append("metadata")
        return list(dict.fromkeys(changed))

    def _conflict_reason(self, goldfinger: Goldfinger, payload: dict[str, Any], *, override: bool) -> str | None:
        if override:
            return None
        owner_id, owner_name = self._owner_snapshot(goldfinger.project_id, payload)
        if owner_id and goldfinger.owner_character_id and owner_id != goldfinger.owner_character_id:
            return "owner_ambiguity"
        if owner_name and goldfinger.owner_character_name and self._normalize(owner_name) != self._normalize(goldfinger.owner_character_name):
            return "owner_ambiguity"
        if payload.get("type") and goldfinger.type and payload.get("type") != goldfinger.type:
            return "normalized_name_collision"
        status = payload.get("status")
        if status and status != "unknown" and goldfinger.status not in (None, "unknown", status):
            return "status_contradiction"
        for field in ("rules", "limits"):
            incoming = payload.get(field)
            existing = getattr(goldfinger, field)
            if incoming and existing and not self._json_equal(incoming, existing):
                return f"core_{field}_contradiction"
        if payload.get("summary") and goldfinger.summary and payload["summary"] != goldfinger.summary and goldfinger.summary not in payload["summary"]:
            return "summary_conflict"
        return None

    def _get_or_record_candidate(self, run: ExtractionRun, payload: dict[str, Any]) -> ExtractionCandidate:
        key = self._candidate_key(run.id, payload)
        existing = self.db.execute(
            select(ExtractionCandidate).where(
                ExtractionCandidate.run_id == run.id,
                ExtractionCandidate.candidate_type == "goldfinger",
            )
        ).scalars().all()
        for candidate in existing:
            if self._payload(candidate).get("goldfinger_sync_key") == key:
                return candidate
        candidate_payload = {**payload, "goldfinger_sync_key": key}
        return ChapterFactSyncService(self.db).record_candidate(
            run.id,
            "goldfinger",
            candidate_payload,
            float(payload.get("confidence") or 0.0),
            str(payload.get("evidence_excerpt") or ""),
            "goldfinger_auto_merge_pending",
        )

    @dataclass(slots=True)
    class _TargetResolution:
        goldfinger: Goldfinger | None
        reason: str | None = None

    def _resolve_target(self, project_id: str, payload: dict[str, Any], *, target_id: str | None, override: bool) -> _TargetResolution:
        if target_id:
            target = self.db.get(Goldfinger, target_id)
            if target is None or target.project_id != project_id:
                return self._TargetResolution(None, "goldfinger_target_not_found")
            return self._TargetResolution(target)
        matches = self.db.execute(
            select(Goldfinger).where(
                Goldfinger.project_id == project_id,
                Goldfinger.normalized_name == payload.get("normalized_name"),
            )
        ).scalars().all()
        if not matches:
            return self._TargetResolution(None)
        owner_id = payload.get("owner_character_id")
        goldfinger_type = payload.get("type")
        narrowed = [row for row in matches if (not owner_id or row.owner_character_id == owner_id) and (not goldfinger_type or row.type in (None, goldfinger_type))]
        if len(narrowed) == 1:
            return self._TargetResolution(narrowed[0])
        if len(matches) == 1 and not owner_id and not goldfinger_type:
            return self._TargetResolution(matches[0])
        if override and narrowed:
            return self._TargetResolution(sorted(narrowed, key=lambda row: row.id)[0])
        return self._TargetResolution(None, "normalized_name_collision")

    def _resolve_owner(self, project_id: str, payload: dict[str, Any]) -> str | None:
        owner_id = payload.get("owner_character_id")
        owner_name = payload.get("owner_character_name")
        if owner_id:
            owner = self.db.get(Character, owner_id)
            if owner is None or owner.project_id != project_id:
                return "owner_ambiguity"
            payload["owner_character_name"] = owner.name
            return None
        if owner_name:
            matches = self._characters_by_name(project_id, str(owner_name))
            if len(matches) != 1:
                return "owner_ambiguity"
            payload["owner_character_id"] = matches[0].id
            payload["owner_character_name"] = matches[0].name
        return None

    def _owner_snapshot(self, project_id: str, payload: dict[str, Any]) -> tuple[str | None, str | None]:
        _ = self._resolve_owner(project_id, payload)
        return self._text(payload.get("owner_character_id")), self._text(payload.get("owner_character_name"))

    def _characters_by_name(self, project_id: str, name: str) -> list[Character]:
        normalized = self._normalize(name)
        rows = self.db.execute(select(Character).where(Character.project_id == project_id)).scalars().all()
        return [row for row in rows if self._normalize(row.name) == normalized]

    def _get_or_create_provenance(self, candidate: ExtractionCandidate, goldfinger_id: str) -> EntityProvenance:
        existing = self.db.execute(
            select(EntityProvenance).where(
                EntityProvenance.project_id == candidate.project_id,
                EntityProvenance.entity_type == "goldfinger",
                EntityProvenance.entity_id == goldfinger_id,
                EntityProvenance.source_type == "extraction_candidate",
                EntityProvenance.source_id == candidate.id,
                EntityProvenance.candidate_id == candidate.id,
                EntityProvenance.claim_type == "goldfinger_claim",
                EntityProvenance.status == "active",
            )
        ).scalars().first()
        if existing is not None:
            return existing
        provenance = EntityProvenance(
            id=str(uuid.uuid4()),
            project_id=candidate.project_id,
            entity_type="goldfinger",
            entity_id=goldfinger_id,
            source_type="extraction_candidate",
            source_id=candidate.id,
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            chapter_id=candidate.source_chapter_id,
            claim_type="goldfinger_claim",
            claim_payload=self._payload(candidate),
            evidence_text=candidate.evidence_text,
            source_start=candidate.source_start_offset,
            source_end=candidate.source_end_offset,
            confidence=candidate.confidence,
            status="active",
            created_by=candidate.reviewer_user_id or GOLDFINGER_SYNC_CREATED_BY,
        )
        self.db.add(provenance)
        self.db.flush()
        return provenance

    def _set_decision(self, candidate: ExtractionCandidate, *, action: str, reason: str | None, **extra: Any) -> None:
        payload = self._payload(candidate)
        candidate.payload = {
            **payload,
            "merge_decision": {
                "service": GOLDFINGER_SYNC_CREATED_BY,
                "action": action,
                "reason": reason,
                "decided_at": self._now().isoformat(),
                **extra,
            },
        }

    def _require_run(self, run_id: str) -> ExtractionRun:
        run = self.db.get(ExtractionRun, run_id)
        if run is None:
            raise ValueError(f"sync run not found: {run_id}")
        return run

    def _require_candidate(self, candidate_id: str) -> ExtractionCandidate:
        candidate = self.db.get(ExtractionCandidate, candidate_id)
        if candidate is None:
            raise ValueError(f"candidate not found: {candidate_id}")
        return candidate

    @staticmethod
    def _payload(candidate: ExtractionCandidate) -> dict[str, Any]:
        return dict(candidate.payload) if isinstance(candidate.payload, dict) else {}

    @staticmethod
    def _candidate_key(run_id: str, payload: dict[str, Any]) -> str:
        stable = {key: payload.get(key) for key in GOLDFINGER_REQUIRED_CHANGE_FIELDS}
        encoded = json.dumps({"run_id": run_id, "payload": stable}, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_json_list(existing: Any, incoming: Any) -> list[Any]:
        merged = list(existing) if isinstance(existing, list) else ([] if existing is None else [existing])
        for item in incoming if isinstance(incoming, list) else ([] if incoming is None else [incoming]):
            marker = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if all(json.dumps(current, ensure_ascii=False, sort_keys=True, default=str) != marker for current in merged):
                merged.append(item)
        return merged

    @classmethod
    def _merge_metadata(cls, existing: Any, incoming: Any) -> dict[str, Any]:
        merged = dict(existing) if isinstance(existing, dict) else {}
        if not isinstance(incoming, dict):
            return merged
        for key, value in incoming.items():
            if key == "usage_examples":
                merged[key] = cls._merge_json_list(merged.get(key), value)
            elif key not in merged:
                merged[key] = value
        return merged

    @staticmethod
    def _json_equal(left: Any, right: Any) -> bool:
        return json.dumps(left, ensure_ascii=False, sort_keys=True, default=str) == json.dumps(right, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _normalize(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _listish(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        return [item for item in (cls._text(entry) for entry in cls._listish(value)) if item]

    @staticmethod
    def _jsonish(value: Any) -> Any:
        return value if value not in (None, "") else None


def accept_goldfinger_candidate(db: Session, candidate_id: str, **kwargs: Any) -> GoldfingerSyncResult:
    """Convenience wrapper for router/tests."""

    return GoldfingerSyncService(db).accept_candidate(candidate_id, **kwargs)
