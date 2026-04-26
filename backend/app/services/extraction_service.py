"""Chapter text extraction core.

This service is intentionally limited to staging extraction runs and pending
candidates from already-persisted chapter content. It does not promote any
candidate into canonical character, organization, timeline, provenance, or world
setting rows; later review/merge tasks own those mutations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Callable, Protocol, TypeAlias, cast
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.project import Project
from app.models.relationship import ExtractionCandidate, ExtractionRun


EXTRACTION_PIPELINE_VERSION = "extraction-core-v1"
EXTRACTION_SCHEMA_VERSION = "novel-extraction-schema-v1"
EXTRACTION_PROMPT_VERSION = "novel-extraction-prompt-v1"

SUPPORTED_CANDIDATE_TYPES = {
    "character",
    "organization",
    "profession",
    "relationship",
    "organization_affiliation",
    "profession_assignment",
    "world_fact",
    "character_state",
}

CANONICAL_TARGET_TYPES = {
    "character": "character",
    "organization": "organization",
    "profession": "career",
    "relationship": None,
    "organization_affiliation": "organization",
    "profession_assignment": "career",
    "world_fact": None,
    "character_state": "character",
}

EXTRACTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "schema_version": EXTRACTION_SCHEMA_VERSION,
    "prompt_version": EXTRACTION_PROMPT_VERSION,
    "type": "object",
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "candidate_type",
                    "confidence",
                    "evidence_text",
                    "source",
                ],
                "properties": {
                    "candidate_type": {"enum": sorted(SUPPORTED_CANDIDATE_TYPES)},
                    "name": {"type": "string"},
                    "display_name": {"type": "string"},
                    "normalized_name": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_text": {"type": "string"},
                    "story_time_label": {"type": "string"},
                    "source": {
                        "type": "object",
                        "required": ["chapter", "order", "offset_start", "offset_end"],
                        "properties": {
                            "chapter_id": {"type": "string"},
                            "chapter": {"type": "integer"},
                            "order": {"type": "integer"},
                            "offset_start": {"type": "integer"},
                            "offset_end": {"type": "integer"},
                        },
                    },
                    "payload": {"type": "object"},
                },
            },
        }
    },
}


RawExtractionOutput: TypeAlias = dict[str, Any] | list[Any] | str


@dataclass(slots=True)
class ExtractionContext:
    """Stable context passed to a model/fake extractor."""

    project_id: str
    user_id: str
    chapter_id: str
    chapter_number: int
    chapter_order: int
    schema_version: str = EXTRACTION_SCHEMA_VERSION
    prompt_version: str = EXTRACTION_PROMPT_VERSION
    pipeline_version: str = EXTRACTION_PIPELINE_VERSION
    trigger_source: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)


class ExtractionCallable(Protocol):
    def __call__(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        project: Project,
        chapter: Chapter,
        context: ExtractionContext,
    ) -> RawExtractionOutput:
        ...


def normalize_extraction_name(value: Any) -> str:
    """Normalize names/aliases for deterministic candidate lookup payloads."""

    text = str(value or "").strip().lower()
    return " ".join(text.split())


def build_extraction_prompt(project: Project, chapter: Chapter) -> str:
    """Build the strict structured prompt contract for chapter extraction."""

    content = chapter.content or ""
    return f"""<system>
你是小说正文结构化抽取器。只根据已提供的章节正文抽取候选事实，不创建或合并规范实体。
</system>

<task>
从持久化章节正文中抽取待审核候选，候选类型只能是：
character, organization, profession, relationship, organization_affiliation,
profession_assignment, world_fact, character_state。
</task>

<context>
项目ID：{project.id}
项目标题：{project.title}
章节ID：{chapter.id}
章节序号：{chapter.chapter_number}
章节标题：{chapter.title}
schema_version：{EXTRACTION_SCHEMA_VERSION}
prompt_version：{EXTRACTION_PROMPT_VERSION}
</context>

<chapter_content>
{content}
</chapter_content>

<output>
仅输出一个纯JSON对象，不要markdown、代码块或解释。格式：
{{
  "candidates": [
    {{
      "candidate_type": "character",
      "name": "名称或事实主体",
      "normalized_name": "可选；如省略由系统规范化",
      "aliases": ["可选别名"],
      "confidence": 0.0,
      "evidence_text": "与正文source偏移完全一致的原文",
      "source": {{"chapter_id": "{chapter.id}", "chapter": {chapter.chapter_number}, "order": 1, "offset_start": 0, "offset_end": 1}},
      "story_time_label": "可选故事时间",
      "payload": {{"保留候选事实字段": "值"}}
    }}
  ]
}}
</output>"""


class ExtractionValidationError(ValueError):
    """Raised when model output cannot be converted into pending candidates."""


class ExtractionService:
    """Persist extraction runs and pending candidates for one chapter."""

    def __init__(self, db: Session) -> None:
        self.db: Session = db

    def extract_chapter(
        self,
        *,
        project_id: str,
        chapter_id: str,
        user_id: str,
        extractor: ExtractionCallable | Callable[..., RawExtractionOutput],
        force: bool = False,
        trigger_source: str = "manual",
        provider: str | None = None,
        model: str | None = None,
        reasoning_intensity: str | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> ExtractionRun:
        """Extract pending candidates from persisted ``Chapter.content``.

        If an unchanged completed run already exists for the same project,
        chapter, content hash, schema version, and prompt hash, that run is
        returned unless ``force`` is true.
        """

        project = self._get_project(project_id)
        chapter = self._get_chapter(project_id, chapter_id)
        content = chapter.content or ""
        content_hash = self._hash_text(content)
        prompt = build_extraction_prompt(project, chapter)
        prompt_hash = self._hash_text(f"{EXTRACTION_PROMPT_VERSION}\n{prompt}")

        if not force:
            existing = self._find_completed_run(
                project_id=project.id,
                chapter_id=chapter.id,
                content_hash=content_hash,
                prompt_hash=prompt_hash,
            )
            if existing is not None:
                return existing

        run = ExtractionRun(
            id=str(uuid.uuid4()),
            project_id=project.id,
            chapter_id=chapter.id,
            trigger_source=trigger_source,
            pipeline_version=EXTRACTION_PIPELINE_VERSION,
            schema_version=EXTRACTION_SCHEMA_VERSION,
            prompt_hash=prompt_hash,
            content_hash=content_hash,
            status="running",
            provider=provider,
            model=model,
            reasoning_intensity=reasoning_intensity,
            run_metadata={
                "prompt_version": EXTRACTION_PROMPT_VERSION,
                "schema_version": EXTRACTION_SCHEMA_VERSION,
                "pipeline_version": EXTRACTION_PIPELINE_VERSION,
                "trigger_source": trigger_source,
                "chapter_number": chapter.chapter_number,
                "chapter_title": chapter.title,
                "content_length": len(content),
                "source_metadata": source_metadata or {},
            },
            started_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.db.add(run)
        self.db.flush()

        if not content.strip():
            return self._fail_run(run, raw_response=None, error_message="chapter content is empty")

        context = ExtractionContext(
            project_id=project.id,
            user_id=user_id,
            chapter_id=chapter.id,
            chapter_number=int(chapter.chapter_number),
            chapter_order=int(chapter.sub_index or 1),
            trigger_source=trigger_source,
            metadata=source_metadata or {},
        )

        try:
            raw_output = extractor(
                prompt=prompt,
                schema=EXTRACTION_OUTPUT_SCHEMA,
                project=project,
                chapter=chapter,
                context=context,
            )
            normalized_output = self._parse_model_output(raw_output)
            candidates = self._validate_candidates(
                normalized_output,
                run=run,
                chapter=chapter,
                user_id=user_id,
                trigger_source=trigger_source,
                source_hash=content_hash,
                provider=provider,
                model=model,
                reasoning_intensity=reasoning_intensity,
            )
        except Exception as exc:
            return self._fail_run(run, raw_response=locals().get("raw_output"), error_message=str(exc))

        run.raw_response = self._json_safe(normalized_output)
        run.status = "completed"
        run.completed_at = datetime.now(UTC).replace(tzinfo=None)
        run.error_message = None
        for candidate in candidates:
            self.db.add(candidate)
        self.db.flush()
        return run

    def _get_project(self, project_id: str) -> Project:
        project = self.db.get(Project, project_id)
        if project is None:
            raise ValueError(f"project not found: {project_id}")
        return project

    def _get_chapter(self, project_id: str, chapter_id: str) -> Chapter:
        chapter = self.db.get(Chapter, chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise ValueError(f"chapter not found in project: {chapter_id}")
        return chapter

    def _find_completed_run(
        self,
        *,
        project_id: str,
        chapter_id: str,
        content_hash: str,
        prompt_hash: str,
    ) -> ExtractionRun | None:
        return self.db.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.project_id == project_id,
                ExtractionRun.chapter_id == chapter_id,
                ExtractionRun.content_hash == content_hash,
                ExtractionRun.schema_version == EXTRACTION_SCHEMA_VERSION,
                ExtractionRun.prompt_hash == prompt_hash,
                ExtractionRun.status == "completed",
            )
            .order_by(ExtractionRun.created_at.desc())
        ).scalars().first()

    def _fail_run(self, run: ExtractionRun, *, raw_response: Any, error_message: str) -> ExtractionRun:
        run.status = "failed"
        run.error_message = error_message[:4000]
        run.raw_response = self._json_safe(raw_response)
        run.completed_at = datetime.utcnow()
        self.db.flush()
        return run

    def _parse_model_output(self, raw_output: RawExtractionOutput) -> dict[str, Any]:
        if isinstance(raw_output, str):
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise ExtractionValidationError(f"model output is not valid JSON: {exc}") from exc
        else:
            parsed = raw_output

        if isinstance(parsed, list):
            parsed = {"candidates": parsed}
        if not isinstance(parsed, dict):
            raise ExtractionValidationError("model output must be a JSON object")

        candidates = parsed.get("candidates")
        if not isinstance(candidates, list):
            raise ExtractionValidationError("model output must contain candidates array")
        return parsed

    def _validate_candidates(
        self,
        model_output: dict[str, Any],
        *,
        run: ExtractionRun,
        chapter: Chapter,
        user_id: str,
        trigger_source: str,
        source_hash: str,
        provider: str | None,
        model: str | None,
        reasoning_intensity: str | None,
    ) -> list[ExtractionCandidate]:
        raw_candidates = model_output.get("candidates")
        if not isinstance(raw_candidates, list):
            raise ExtractionValidationError("candidates must be an array")

        candidates: list[ExtractionCandidate] = []
        for index, raw_candidate in enumerate(raw_candidates):
            if not isinstance(raw_candidate, dict):
                raise ExtractionValidationError(f"candidates[{index}] must be an object")
            candidates.append(
                self._build_candidate(
                    raw_candidate,
                    index=index,
                    run=run,
                    chapter=chapter,
                    user_id=user_id,
                    trigger_source=trigger_source,
                    source_hash=source_hash,
                    provider=provider,
                    model=model,
                    reasoning_intensity=reasoning_intensity,
                )
            )
        return candidates

    def _build_candidate(
        self,
        raw: dict[str, Any],
        *,
        index: int,
        run: ExtractionRun,
        chapter: Chapter,
        user_id: str,
        trigger_source: str,
        source_hash: str,
        provider: str | None,
        model: str | None,
        reasoning_intensity: str | None,
    ) -> ExtractionCandidate:
        candidate_type = str(raw.get("candidate_type") or raw.get("type") or "").strip()
        if candidate_type not in SUPPORTED_CANDIDATE_TYPES:
            raise ExtractionValidationError(f"candidates[{index}].candidate_type is invalid: {candidate_type!r}")

        confidence = raw.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ExtractionValidationError(f"candidates[{index}].confidence must be between 0 and 1")

        evidence_text = raw.get("evidence_text")
        if not isinstance(evidence_text, str) or not evidence_text:
            raise ExtractionValidationError(f"candidates[{index}].evidence_text is required")

        source = raw.get("source")
        if not isinstance(source, dict):
            raise ExtractionValidationError(f"candidates[{index}].source is required")

        offset_start = source.get("offset_start", source.get("source_start_offset"))
        offset_end = source.get("offset_end", source.get("source_end_offset"))
        source_order = source.get("order", source.get("chapter_order"))
        if not isinstance(offset_start, int) or isinstance(offset_start, bool):
            raise ExtractionValidationError(f"candidates[{index}].source.offset_start is required")
        if not isinstance(offset_end, int) or isinstance(offset_end, bool):
            raise ExtractionValidationError(f"candidates[{index}].source.offset_end is required")
        if not isinstance(source_order, int) or isinstance(source_order, bool):
            raise ExtractionValidationError(f"candidates[{index}].source.order is required")
        if offset_start < 0 or offset_end <= offset_start:
            raise ExtractionValidationError(f"candidates[{index}].source offsets must form a non-empty span")

        source_chapter_id = source.get("chapter_id")
        if source_chapter_id is not None and str(source_chapter_id) != chapter.id:
            raise ExtractionValidationError(f"candidates[{index}].source.chapter_id does not match persisted chapter")
        source_chapter_number = source.get("chapter", source.get("chapter_number"))
        if source_chapter_number is not None and source_chapter_number != chapter.chapter_number:
            raise ExtractionValidationError(f"candidates[{index}].source.chapter does not match persisted chapter")

        content = chapter.content or ""
        if offset_end > len(content):
            raise ExtractionValidationError(f"candidates[{index}].source.offset_end is outside chapter content")
        if content[offset_start:offset_end] != evidence_text:
            raise ExtractionValidationError(f"candidates[{index}].source span must match evidence_text")

        display_name = self._candidate_display_name(raw, candidate_type)
        normalized_name = normalize_extraction_name(raw.get("normalized_name") or display_name)
        aliases_raw = raw.get("aliases")
        aliases: list[object] = aliases_raw if isinstance(aliases_raw, list) else []
        clean_aliases = [str(alias).strip() for alias in aliases if str(alias or "").strip()]
        normalized_aliases = [normalize_extraction_name(alias) for alias in clean_aliases]

        payload = self._candidate_payload(
            raw,
            candidate_type=candidate_type,
            display_name=display_name,
            normalized_name=normalized_name,
            aliases=clean_aliases,
            normalized_aliases=normalized_aliases,
            chapter=chapter,
            source_order=source_order,
            offset_start=offset_start,
            offset_end=offset_end,
            evidence_text=evidence_text,
            confidence=float(confidence),
        )

        return ExtractionCandidate(
            id=str(uuid.uuid4()),
            run_id=run.id,
            project_id=run.project_id,
            user_id=user_id,
            source_chapter_id=chapter.id,
            source_chapter_start_id=chapter.id,
            source_chapter_end_id=chapter.id,
            candidate_type=candidate_type,
            trigger_type=trigger_source,
            source_hash=source_hash,
            provider=provider,
            model=model,
            reasoning_intensity=reasoning_intensity,
            display_name=display_name,
            normalized_name=normalized_name,
            canonical_target_type=CANONICAL_TARGET_TYPES[candidate_type],
            canonical_target_id=None,
            status="pending",
            confidence=float(confidence),
            evidence_text=evidence_text,
            source_start_offset=offset_start,
            source_end_offset=offset_end,
            source_chapter_number=chapter.chapter_number,
            source_chapter_order=source_order,
            valid_from_chapter_id=chapter.id,
            valid_from_chapter_order=source_order,
            valid_to_chapter_id=None,
            valid_to_chapter_order=None,
            story_time_label=self._optional_text(raw.get("story_time_label")),
            payload=payload,
            raw_payload=self._json_safe(raw),
        )

    def _candidate_display_name(self, raw: dict[str, Any], candidate_type: str) -> str | None:
        keys_by_type = {
            "character": ["display_name", "canonical_name", "name", "character"],
            "organization": ["display_name", "canonical_name", "name", "organization"],
            "profession": ["display_name", "profession", "name"],
            "relationship": ["display_name", "relationship", "name"],
            "organization_affiliation": ["display_name", "current_organization", "organization", "name", "character"],
            "profession_assignment": ["display_name", "profession", "name", "character"],
            "world_fact": ["display_name", "subject", "fact_type", "name"],
            "character_state": ["display_name", "character", "state", "name"],
        }
        for key in keys_by_type[candidate_type]:
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _candidate_payload(
        self,
        raw: dict[str, Any],
        *,
        candidate_type: str,
        display_name: str | None,
        normalized_name: str,
        aliases: list[str],
        normalized_aliases: list[str],
        chapter: Chapter,
        source_order: int,
        offset_start: int,
        offset_end: int,
        evidence_text: str,
        confidence: float,
    ) -> dict[str, Any]:
        raw_payload = raw.get("payload")
        base_payload = cast(dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
        payload: dict[str, Any] = dict(base_payload)
        payload.update({
            "candidate_type": candidate_type,
            "display_name": display_name,
            "normalized_name": normalized_name,
            "aliases": aliases,
            "normalized_aliases": normalized_aliases,
            "confidence": confidence,
            "evidence_text": evidence_text,
            "source": {
                "chapter_id": chapter.id,
                "chapter": chapter.chapter_number,
                "order": source_order,
                "offset_start": offset_start,
                "offset_end": offset_end,
            },
        })
        return self._json_safe(payload)

    def _json_safe(self, value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    def _optional_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_chapter_candidates(
    db: Session,
    *,
    project_id: str,
    chapter_id: str,
    user_id: str,
    extractor: ExtractionCallable | Callable[..., RawExtractionOutput],
    force: bool = False,
    trigger_source: str = "manual",
    provider: str | None = None,
    model: str | None = None,
    reasoning_intensity: str | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> ExtractionRun:
    """Convenience wrapper for one-shot extraction from sync tests/services."""

    return ExtractionService(db).extract_chapter(
        project_id=project_id,
        chapter_id=chapter_id,
        user_id=user_id,
        extractor=extractor,
        force=force,
        trigger_source=trigger_source,
        provider=provider,
        model=model,
        reasoning_intensity=reasoning_intensity,
        source_metadata=source_metadata,
    )
