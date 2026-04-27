"""Shared chapter fact synchronization orchestration.

This module intentionally stages generic extraction runs and review candidates
only. It does not call an LLM, wire chapter-save hooks, or implement
goldfinger-specific extraction/merge logic.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
import hashlib
import json
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.project import Project
from app.models.relationship import ExtractionCandidate, ExtractionRun


CHAPTER_FACT_SYNC_PIPELINE_VERSION = "chapter-fact-sync-v1"
CHAPTER_FACT_SYNC_SCHEMA_VERSION = "chapter-fact-sync-review-v1"
CHAPTER_FACT_SYNC_EXTRACTOR_VERSION = "chapter-fact-sync-extractor-v1"
DEFAULT_CHAPTER_FACT_ENTITY_TYPES = ("relationship", "goldfinger")
SUPPORTED_CHAPTER_FACT_ENTITY_TYPES = {"relationship", "goldfinger", "world_fact"}


CandidateProcessor = Callable[[ExtractionRun], Iterable[dict[str, Any]]]


class ChapterFactSyncService:
    """Coordinate idempotent chapter fact sync runs and pending candidates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def build_idempotency_key(
        chapter_id: str,
        content_hash_or_version: str,
        extractor_version: str,
        entity_type: str,
    ) -> str:
        """Build a deterministic key for one chapter/content/extractor/entity tuple."""

        payload = {
            "chapter_id": str(chapter_id),
            "content_hash_or_version": str(content_hash_or_version),
            "entity_type": str(entity_type).strip().lower(),
            "extractor_version": str(extractor_version),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def schedule_for_chapter(
        self,
        *,
        project_id: str,
        chapter_id: str,
        content: str,
        source: str,
        entity_types: Iterable[str] | None = None,
        extractor_version: str = CHAPTER_FACT_SYNC_EXTRACTOR_VERSION,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[ExtractionRun]:
        """Persist pending sync runs, reusing existing rows by idempotency key.

        One pending/completed/failed run row is created per unique
        chapter/content/extractor/entity type. Duplicate calls return the
        previously persisted run instead of creating duplicates.
        """

        project = self._require_project(project_id)
        chapter = self._require_chapter(project.id, chapter_id)
        content_hash = self._hash_text(content or "")
        trigger_source = str(source or "manual").strip() or "manual"

        runs: list[ExtractionRun] = []
        for entity_type in self._normalize_entity_types(entity_types):
            idempotency_key = self.build_idempotency_key(
                chapter.id,
                content_hash,
                extractor_version,
                entity_type,
            )
            existing = self._find_idempotent_run(
                project_id=project.id,
                chapter_id=chapter.id,
                content_hash=content_hash,
                idempotency_key=idempotency_key,
                entity_type=entity_type,
            )
            if existing is not None:
                runs.append(existing)
                continue

            run = ExtractionRun(
                id=str(uuid.uuid4()),
                project_id=project.id,
                chapter_id=chapter.id,
                trigger_source=trigger_source,
                pipeline_version=CHAPTER_FACT_SYNC_PIPELINE_VERSION,
                schema_version=self._schema_version(entity_type),
                prompt_hash=idempotency_key,
                content_hash=content_hash,
                status="pending",
                run_metadata={
                    "idempotency_key": idempotency_key,
                    "entity_type": entity_type,
                    "extractor_version": extractor_version,
                    "pipeline_version": CHAPTER_FACT_SYNC_PIPELINE_VERSION,
                    "schema_version": self._schema_version(entity_type),
                    "trigger_source": trigger_source,
                    "source": trigger_source,
                    "source_metadata": source_metadata or {},
                    "chapter_number": chapter.chapter_number,
                    "chapter_title": chapter.title,
                    "content_length": len(content or ""),
                },
            )
            self.db.add(run)
            self.db.flush()
            runs.append(run)
        return runs

    def process_run(
        self,
        run_id: str,
        *,
        processor: CandidateProcessor | None = None,
    ) -> ExtractionRun:
        """Process a pending/failed run with an injected processor.

        The default processor is a no-op that completes the run without
        creating candidates. Real extraction is deliberately injected by future
        tasks/workers and is not called inline from API or chapter-save paths.
        """

        run = self._require_run(run_id)
        if run.status not in {"pending", "failed"}:
            raise ValueError(f"run is not processable: {run.status}")

        run.status = "running"
        run.started_at = self._now()
        run.completed_at = None
        self.db.flush()

        try:
            raw_candidates = list(processor(run) if processor is not None else [])
            created_candidate_ids: list[str] = []
            for raw in raw_candidates:
                raw_payload = raw.get("payload")
                candidate_payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else dict(raw)
                candidate = self.record_candidate(
                    run.id,
                    entity_type=str(raw.get("entity_type") or raw.get("candidate_type") or self._entity_type_for_run(run)),
                    payload=candidate_payload,
                    confidence=float(raw.get("confidence", 0.0)),
                    evidence_excerpt=str(raw.get("evidence_excerpt") or raw.get("evidence_text") or ""),
                    review_required_reason=str(raw.get("review_required_reason") or "manual_review_required"),
                )
                created_candidate_ids.append(candidate.id)
            run.status = "completed"
            run.error_message = None
            run.raw_response = {"created_candidate_ids": created_candidate_ids}
            run.completed_at = self._now()
            self.db.flush()
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)[:4000]
            run.completed_at = self._now()
            metadata = self._metadata(run)
            failures = list(metadata.get("failure_history") or [])
            failures.append({"error_message": run.error_message, "failed_at": run.completed_at.isoformat()})
            metadata["failure_history"] = failures
            metadata["last_error_message"] = run.error_message
            run.run_metadata = metadata
            self.db.flush()
            return run

    def retry_run(self, run_id: str) -> ExtractionRun:
        """Move a pending/failed run back to pending and audit retry metadata."""

        run = self._require_run(run_id)
        if run.status not in {"pending", "failed"}:
            raise ValueError(f"run cannot be retried from status: {run.status}")

        metadata = self._metadata(run)
        retry_count = int(metadata.get("retry_count") or 0) + 1
        retry_history = list(metadata.get("retry_history") or [])
        retry_history.append({
            "retry_count": retry_count,
            "previous_status": run.status,
            "previous_error_message": run.error_message,
            "previous_completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "retried_at": self._now().isoformat(),
        })
        metadata["retry_count"] = retry_count
        metadata["retry_history"] = retry_history
        if run.error_message:
            metadata["last_error_message"] = run.error_message

        run.status = "pending"
        run.started_at = None
        run.completed_at = None
        run.error_message = None
        run.run_metadata = metadata
        self.db.flush()
        return run

    def record_candidate(
        self,
        run_id: str,
        entity_type: str,
        payload: dict[str, Any],
        confidence: float,
        evidence_excerpt: str,
        review_required_reason: str,
    ) -> ExtractionCandidate:
        """Create a pending review candidate for a sync run."""

        run = self._require_run(run_id)
        project = self._require_project(run.project_id)
        entity_type = self._normalize_entity_type(entity_type)
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

        safe_payload = self._json_safe(dict(payload or {}))
        evidence = str(evidence_excerpt or "")
        start_offset = self._payload_int(safe_payload, "source_start_offset", "offset_start", default=0)
        end_offset = self._payload_int(
            safe_payload,
            "source_end_offset",
            "offset_end",
            default=start_offset + len(evidence),
        )
        source_order = self._payload_int(safe_payload, "source_chapter_order", "order", default=1)
        display_name = self._display_name(safe_payload, entity_type)
        normalized_name = self._normalize_text(safe_payload.get("normalized_name") or display_name or entity_type)

        candidate = ExtractionCandidate(
            id=str(uuid.uuid4()),
            run_id=run.id,
            project_id=run.project_id,
            user_id=str(project.user_id),
            source_chapter_id=run.chapter_id,
            source_chapter_start_id=run.chapter_id,
            source_chapter_end_id=run.chapter_id,
            candidate_type=entity_type,
            trigger_type=run.trigger_source,
            source_hash=self._candidate_source_hash(run, entity_type, safe_payload, evidence),
            display_name=display_name,
            normalized_name=normalized_name,
            canonical_target_type=None,
            canonical_target_id=None,
            status="pending",
            confidence=float(confidence),
            evidence_text=evidence,
            source_start_offset=start_offset,
            source_end_offset=end_offset,
            source_chapter_number=self._chapter_number(run.chapter_id),
            source_chapter_order=source_order,
            valid_from_chapter_id=run.chapter_id,
            valid_from_chapter_order=source_order,
            story_time_label=self._optional_text(safe_payload.get("story_time_label")),
            payload=safe_payload,
            raw_payload=safe_payload,
            review_required_reason=review_required_reason,
        )
        self.db.add(candidate)
        self.db.flush()
        return candidate

    def _find_idempotent_run(
        self,
        *,
        project_id: str,
        chapter_id: str,
        content_hash: str,
        idempotency_key: str,
        entity_type: str,
    ) -> ExtractionRun | None:
        return self.db.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.project_id == project_id,
                ExtractionRun.chapter_id == chapter_id,
                ExtractionRun.pipeline_version == CHAPTER_FACT_SYNC_PIPELINE_VERSION,
                ExtractionRun.schema_version == self._schema_version(entity_type),
                ExtractionRun.prompt_hash == idempotency_key,
                ExtractionRun.content_hash == content_hash,
            )
            .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        ).scalars().first()

    def _require_project(self, project_id: str) -> Project:
        project = self.db.get(Project, project_id)
        if project is None:
            raise ValueError(f"project not found: {project_id}")
        return project

    def _require_chapter(self, project_id: str, chapter_id: str) -> Chapter:
        chapter = self.db.get(Chapter, chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise ValueError(f"chapter not found in project: {chapter_id}")
        return chapter

    def _require_run(self, run_id: str) -> ExtractionRun:
        run = self.db.get(ExtractionRun, run_id)
        if run is None:
            raise ValueError(f"sync run not found: {run_id}")
        return run

    def _normalize_entity_types(self, entity_types: Iterable[str] | None) -> list[str]:
        raw_types = entity_types or DEFAULT_CHAPTER_FACT_ENTITY_TYPES
        normalized: list[str] = []
        for raw in raw_types:
            entity_type = self._normalize_entity_type(raw)
            if entity_type not in normalized:
                normalized.append(entity_type)
        return normalized

    def _normalize_entity_type(self, entity_type: str) -> str:
        normalized = str(entity_type or "").strip().lower()
        if normalized not in SUPPORTED_CHAPTER_FACT_ENTITY_TYPES:
            raise ValueError(f"unsupported sync entity type: {entity_type}")
        return normalized

    @staticmethod
    def _schema_version(entity_type: str) -> str:
        return f"{CHAPTER_FACT_SYNC_SCHEMA_VERSION}:{entity_type}"

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _metadata(run: ExtractionRun) -> dict[str, Any]:
        return dict(run.run_metadata) if isinstance(run.run_metadata, dict) else {}

    @staticmethod
    def _json_safe(value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    @staticmethod
    def _payload_int(payload: dict[str, Any], *keys: str, default: int) -> int:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        source = payload.get("source")
        if isinstance(source, dict):
            for key in keys:
                value = source.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    return value
        return default

    @staticmethod
    def _display_name(payload: dict[str, Any], entity_type: str) -> str | None:
        keys = [
            "display_name",
            "name",
            "relationship",
            "relationship_name",
            "goldfinger_name",
            "subject",
        ]
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return entity_type

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        return " ".join(text.split())

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _candidate_source_hash(
        self,
        run: ExtractionRun,
        entity_type: str,
        payload: dict[str, Any],
        evidence: str,
    ) -> str:
        encoded = json.dumps(
            {
                "run_id": run.id,
                "content_hash": run.content_hash,
                "entity_type": entity_type,
                "payload": payload,
                "evidence": evidence,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return self._hash_text(encoded)

    def _chapter_number(self, chapter_id: str | None) -> int | None:
        if not chapter_id:
            return None
        chapter = self.db.get(Chapter, chapter_id)
        return int(chapter.chapter_number) if chapter is not None and chapter.chapter_number is not None else None

    def _entity_type_for_run(self, run: ExtractionRun) -> str:
        metadata = self._metadata(run)
        entity_type = metadata.get("entity_type")
        if isinstance(entity_type, str) and entity_type:
            return entity_type
        if run.schema_version and ":" in run.schema_version:
            return run.schema_version.rsplit(":", 1)[-1]
        return "relationship"


def build_idempotency_key(
    chapter_id: str,
    content_hash_or_version: str,
    extractor_version: str,
    entity_type: str,
) -> str:
    """Module-level convenience wrapper for deterministic idempotency keys."""

    return ChapterFactSyncService.build_idempotency_key(
        chapter_id,
        content_hash_or_version,
        extractor_version,
        entity_type,
    )
