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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.logger import get_logger
from app.models.chapter import Chapter
from app.models.project import Project
from app.models.relationship import ExtractionCandidate, ExtractionRun


logger = get_logger(__name__)


EXTRACTION_PIPELINE_VERSION = "extraction-core-v1"
EXTRACTION_SCHEMA_VERSION = "novel-extraction-schema-v1"
EXTRACTION_PROMPT_VERSION = "novel-extraction-prompt-v1"
CHAPTER_COMPLETION_VERSION = "chapter-completion-v1"


def hash_chapter_content(content: str | None) -> str:
    """Return the stable hash carried by chapter-completion tasks."""

    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()

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
        resolved_provider = str(provider or app_settings.default_ai_provider or "unknown")
        resolved_model = str(model or app_settings.default_model or "unknown")
        resolved_reasoning_intensity = str(
            reasoning_intensity or app_settings.default_reasoning_intensity or "auto"
        )
        resolved_source_metadata = dict(source_metadata or {})
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
            provider=resolved_provider,
            model=resolved_model,
            reasoning_intensity=resolved_reasoning_intensity,
            run_metadata={
                "prompt_version": EXTRACTION_PROMPT_VERSION,
                "schema_version": EXTRACTION_SCHEMA_VERSION,
                "pipeline_version": EXTRACTION_PIPELINE_VERSION,
                "trigger_source": trigger_source,
                "chapter_number": chapter.chapter_number,
                "chapter_title": chapter.title,
                "content_length": len(content),
                "source_metadata": resolved_source_metadata,
                "accepted_content_hash": resolved_source_metadata.get("accepted_content_hash"),
                "accepted_content_version": resolved_source_metadata.get("accepted_content_version"),
                "audit": {
                    "provider": resolved_provider,
                    "model": resolved_model,
                    "reasoning_intensity": resolved_reasoning_intensity,
                },
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
            metadata=resolved_source_metadata,
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
                provider=resolved_provider,
                model=resolved_model,
                reasoning_intensity=resolved_reasoning_intensity,
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
            _ = json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    def _optional_text(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


_default_extraction_callable: ExtractionCallable | Callable[..., RawExtractionOutput] | None = None


def set_default_extraction_callable(extractor: ExtractionCallable | Callable[..., RawExtractionOutput] | None) -> None:
    """Set the process-local extractor used by trigger integrations.

    Tests and future async/status workers can install a real extractor without
    coupling persistence routes to provider clients. When unset, trigger runs are
    still recorded deterministically with an empty candidate list.
    """

    global _default_extraction_callable
    _default_extraction_callable = extractor


def get_default_extraction_callable() -> ExtractionCallable | Callable[..., RawExtractionOutput]:
    if _default_extraction_callable is not None:
        return _default_extraction_callable

    def empty_extractor(**_: Any) -> RawExtractionOutput:
        return {"candidates": []}

    return empty_extractor


@dataclass(frozen=True, slots=True)
class ExtractionTriggerResult:
    """Outcome for one extraction trigger attempt."""

    run_id: str
    chapter_id: str
    status: str
    reused_existing_run: bool


class ExtractionTriggerService:
    """Coordinate extraction triggers after persisted chapter text changes."""

    def __init__(self, db: Session) -> None:
        self.db: Session = db

    def trigger_chapter(
        self,
        *,
        project_id: str,
        chapter_id: str,
        user_id: str,
        trigger_source: str,
        force: bool = False,
        extractor: ExtractionCallable | Callable[..., RawExtractionOutput] | None = None,
        enabled: bool = True,
        supersede_prior: bool = True,
        source_metadata: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        reasoning_intensity: str | None = None,
    ) -> ExtractionTriggerResult | None:
        """Run extraction for a persisted chapter if the trigger is enabled."""

        if not enabled:
            return None

        previous_run_ids = set(self._chapter_run_ids(project_id=project_id, chapter_id=chapter_id))
        run = ExtractionService(self.db).extract_chapter(
            project_id=project_id,
            chapter_id=chapter_id,
            user_id=user_id,
            extractor=extractor or get_default_extraction_callable(),
            force=force,
            trigger_source=trigger_source,
            source_metadata=source_metadata,
            provider=provider,
            model=model,
            reasoning_intensity=reasoning_intensity,
        )
        reused_existing_run = run.id in previous_run_ids
        if supersede_prior and not reused_existing_run and run.status == "completed":
            self._supersede_pending_candidates_for_chapter(
                project_id=project_id,
                chapter_id=chapter_id,
                current_run_id=run.id,
            )
        return ExtractionTriggerResult(
            run_id=run.id,
            chapter_id=chapter_id,
            status=str(run.status),
            reused_existing_run=reused_existing_run,
        )

    def trigger_project(
        self,
        *,
        project_id: str,
        user_id: str,
        trigger_source: str = "manual_project",
        force: bool = True,
        extractor: ExtractionCallable | Callable[..., RawExtractionOutput] | None = None,
        enabled: bool = True,
        supersede_prior: bool = False,
    ) -> list[ExtractionTriggerResult]:
        if not enabled:
            return []
        chapters = self._project_chapters(project_id=project_id)
        return [
            result
            for chapter in chapters
            if (
                result := self.trigger_chapter(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    user_id=user_id,
                    trigger_source=trigger_source,
                    force=force,
                    extractor=extractor,
                    enabled=enabled,
                    supersede_prior=supersede_prior,
                    source_metadata={"manual_scope": "project"},
                )
            )
            is not None
        ]

    def trigger_chapter_range(
        self,
        *,
        project_id: str,
        user_id: str,
        start_chapter_number: int,
        end_chapter_number: int,
        trigger_source: str = "manual_range",
        force: bool = True,
        extractor: ExtractionCallable | Callable[..., RawExtractionOutput] | None = None,
        enabled: bool = True,
        supersede_prior: bool = False,
    ) -> list[ExtractionTriggerResult]:
        if not enabled:
            return []
        if end_chapter_number < start_chapter_number:
            raise ValueError("end_chapter_number must be greater than or equal to start_chapter_number")
        chapters = self.db.execute(
            select(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number >= start_chapter_number,
                Chapter.chapter_number <= end_chapter_number,
            )
            .order_by(Chapter.chapter_number.asc(), Chapter.sub_index.asc())
        ).scalars().all()
        return [
            result
            for chapter in chapters
            if (
                result := self.trigger_chapter(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    user_id=user_id,
                    trigger_source=trigger_source,
                    force=force,
                    extractor=extractor,
                    enabled=enabled,
                    supersede_prior=supersede_prior,
                    source_metadata={
                        "manual_scope": "range",
                        "start_chapter_number": start_chapter_number,
                        "end_chapter_number": end_chapter_number,
                    },
                )
            )
            is not None
        ]

    def _project_chapters(self, *, project_id: str) -> list[Chapter]:
        return list(
            self.db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.chapter_number.asc(), Chapter.sub_index.asc())
            ).scalars().all()
        )

    def _chapter_run_ids(self, *, project_id: str, chapter_id: str) -> list[str]:
        return [
            str(run_id)
            for run_id in self.db.execute(
                select(ExtractionRun.id).where(
                    ExtractionRun.project_id == project_id,
                    ExtractionRun.chapter_id == chapter_id,
                )
            ).scalars().all()
        ]

    def _supersede_pending_candidates_for_chapter(
        self,
        *,
        project_id: str,
        chapter_id: str,
        current_run_id: str,
    ) -> None:
        prior_candidates = self.db.execute(
            select(ExtractionCandidate).where(
                ExtractionCandidate.project_id == project_id,
                ExtractionCandidate.source_chapter_id == chapter_id,
                ExtractionCandidate.run_id != current_run_id,
                ExtractionCandidate.status == "pending",
            )
        ).scalars().all()
        for candidate in prior_candidates:
            candidate.status = "superseded"


async def run_extraction_trigger_after_commit(
    db: AsyncSession,
    *,
    project_id: str,
    chapter_id: str,
    user_id: str,
    trigger_source: str,
    force: bool = False,
    extractor: ExtractionCallable | Callable[..., RawExtractionOutput] | None = None,
    enabled: bool | None = None,
    supersede_prior: bool = True,
    source_metadata: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    reasoning_intensity: str | None = None,
) -> ExtractionTriggerResult | None:
    """Best-effort async entrypoint used by route/import persistence flows.

    Call only after the chapter/import/generation transaction has committed.
    Any trigger error is isolated to the extraction transaction and will not
    roll back the already-persisted text.
    """

    if enabled is None:
        enabled = bool(app_settings.EXTRACTION_PIPELINE_ENABLED)
    if not enabled:
        return None
    try:
        result = await db.run_sync(
            lambda session: ExtractionTriggerService(session).trigger_chapter(
                project_id=project_id,
                chapter_id=chapter_id,
                user_id=user_id,
                trigger_source=trigger_source,
                force=force,
                source_metadata=source_metadata,
                provider=provider,
                model=model,
                reasoning_intensity=reasoning_intensity,
            )
        )
        await db.commit()
        return result
    except Exception as exc:
        await db.rollback()
        logger.warning("正文抽取触发失败，已保留已落库正文: %s", exc, exc_info=True)
        return None

async def run_automatic_chapter_extraction_task(
    task_id: str,
    user_id: str,
    project_id: str,
    chapter_id: str,
    accepted_content_hash: str | None = None,
    accepted_content_version: str | None = None,
) -> None:
    """Extract one accepted chapter only while its accepted snapshot is current."""

    if not app_settings.EXTRACTION_PIPELINE_ENABLED:
        logger.info("实体提取管线已禁用，跳过任务 %s", task_id[:8])
        return

    from app.api.settings import get_user_ai_service_from_db
    from app.database import get_engine
    from app.models.background_task import BackgroundTask
    from app.services.background_task_service import TaskProgressTracker
    from app.services.candidate_merge_service import CandidateMergeService
    from app.services.json_helper import clean_json_response

    tracker = TaskProgressTracker(task_id, user_id, "章节实体提取")
    engine = await get_engine(user_id)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def is_cancelled() -> bool:
        check = getattr(tracker, "check_cancelled", None)
        if check is None:
            return False
        return bool(await check())

    async def accepted_state_matches(db: AsyncSession, expected_hash: str, expected_version: str) -> bool:
        result = await db.execute(
            select(Chapter)
            .where(Chapter.id == chapter_id, Chapter.project_id == project_id)
            .execution_options(populate_existing=True)
        )
        current = result.scalar_one_or_none()
        return bool(
            current is not None
            and str(current.status or "").lower() == "completed"
            and expected_version == CHAPTER_COMPLETION_VERSION
            and hash_chapter_content(current.content) == expected_hash
        )

    async def abort(db: AsyncSession, message: str) -> None:
        await db.rollback()
        if not await is_cancelled():
            await tracker.error(message)

    try:
        await tracker.start("正在准备章节实体提取...")
        async with session_factory() as db:
            task = await db.get(BackgroundTask, task_id)
            task_input = task.task_input if task is not None and isinstance(task.task_input, dict) else {}
            expected_hash = str(
                accepted_content_hash
                or task_input.get("accepted_content_hash")
                or task_input.get("content_hash")
                or ""
            )
            expected_version = str(
                accepted_content_version
                or task_input.get("accepted_content_version")
                or task_input.get("content_version")
                or CHAPTER_COMPLETION_VERSION
            )

            chapter = await db.get(Chapter, chapter_id)
            project = await db.get(Project, project_id)
            if chapter is None or chapter.project_id != project_id or project is None:
                raise ValueError("章节不存在或不属于当前项目")
            if not expected_hash:
                expected_hash = hash_chapter_content(chapter.content)
            if not await accepted_state_matches(db, expected_hash, expected_version):
                await abort(db, "章节已变更或未验收，跳过过期实体提取任务")
                return
            if await is_cancelled():
                await abort(db, "实体提取任务已取消")
                return
            if not (chapter.content or "").strip():
                raise ValueError("章节正文为空，无法提取实体")

            await tracker.loading(f"正在读取《{chapter.title}》正文...")
            prompt = build_extraction_prompt(project, chapter)
            ai_service = await get_user_ai_service_from_db(user_id, db)
            resolved_provider = str(
                getattr(ai_service, "api_provider", None)
                or app_settings.default_ai_provider
                or "unknown"
            )
            resolved_model = str(
                getattr(ai_service, "default_model", None)
                or app_settings.default_model
                or "unknown"
            )
            resolved_reasoning = str(
                getattr(ai_service, "default_reasoning_intensity", None)
                or app_settings.default_reasoning_intensity
                or "auto"
            )
            resolver = getattr(ai_service, "_select_reasoning_intensity", None)
            if callable(resolver):
                try:
                    resolved_reasoning = str(
                        resolver(provider=resolved_provider, model=resolved_model)
                        or resolved_reasoning
                    )
                except Exception:
                    logger.debug("无法解析实体提取推理强度，使用服务默认值", exc_info=True)

            await tracker.generating(message="AI 正在识别角色、组织、职业与关系...")
            response = await ai_service.generate_text(
                prompt=prompt,
                temperature=0.1,
                max_tokens=6000,
                system_prompt="你是严谨的小说实体抽取器，只输出符合请求结构的JSON。",
                auto_mcp=False,
                handle_tool_calls=False,
                provider=resolved_provider,
                model=resolved_model,
                reasoning_intensity=resolved_reasoning,
            )
            if await is_cancelled():
                await abort(db, "实体提取任务在AI生成后被取消")
                return
            if not await accepted_state_matches(db, expected_hash, expected_version):
                await abort(db, "章节在AI生成期间发生变更，丢弃过期实体提取结果")
                return

            response_content = response.get("content") if isinstance(response, dict) else response
            raw_output = clean_json_response(str(response_content or ""))
            await tracker.parsing("正在校验实体证据与章节偏移...")

            trigger_result = await db.run_sync(
                lambda session: ExtractionTriggerService(session).trigger_chapter(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    user_id=user_id,
                    trigger_source="chapter_acceptance",
                    force=False,
                    extractor=lambda **_: raw_output,
                    enabled=True,
                    supersede_prior=True,
                    provider=resolved_provider,
                    model=resolved_model,
                    reasoning_intensity=resolved_reasoning,
                    source_metadata={
                        "operation": "chapter_acceptance",
                        "task_id": task_id,
                        "accepted_content_hash": expected_hash,
                        "accepted_content_version": expected_version,
                    },
                )
            )
            if trigger_result is None or trigger_result.status != "completed":
                raise RuntimeError("实体提取结果校验失败")

            # Candidate merge and its canonical relationship writes remain in
            # this transaction. Cancellation/staleness is checked before and
            # after the merge so rollback leaves no partial canonical state.
            if await is_cancelled():
                await abort(db, "实体提取任务在合并前被取消")
                return
            if not await accepted_state_matches(db, expected_hash, expected_version):
                await abort(db, "章节在合并前发生变更，丢弃过期实体提取结果")
                return

            await tracker.saving("正在匹配已有实体并建立高置信关系...")

            def post_process(session: Session) -> dict[str, Any]:
                merge_service = CandidateMergeService(session)
                similarity = merge_service.stage_similar_pending(run_id=trigger_result.run_id)
                accepted_relationships = merge_service.auto_accept_safe_relationships(run_id=trigger_result.run_id)
                candidates = session.execute(
                    select(ExtractionCandidate).where(ExtractionCandidate.run_id == trigger_result.run_id)
                ).scalars().all()
                counts: dict[str, int] = {}
                pending_count = 0
                for candidate in candidates:
                    counts[candidate.candidate_type] = counts.get(candidate.candidate_type, 0) + 1
                    if candidate.status == "pending":
                        pending_count += 1
                session.flush()
                return {
                    "candidate_count": len(candidates),
                    "pending_count": pending_count,
                    "counts": counts,
                    "similarity": similarity,
                    "accepted_relationships": accepted_relationships,
                }

            summary = await db.run_sync(post_process)
            if await is_cancelled():
                await abort(db, "实体提取任务在提交前被取消")
                return
            if not await accepted_state_matches(db, expected_hash, expected_version):
                await abort(db, "章节在提交前发生变更，丢弃过期实体提取结果")
                return
            await db.commit()
            task_result = {
                "project_id": project_id,
                "chapter_id": chapter_id,
                "chapter_title": chapter.title,
                "run_id": trigger_result.run_id,
                **summary,
            }
            await tracker.complete(
                f"《{chapter.title}》实体提取完成：发现 {summary['candidate_count']} 条候选，{summary['pending_count']} 条待审核",
                result=task_result,
            )
    except Exception as exc:
        logger.error("章节验收实体提取失败: %s", exc, exc_info=True)
        await tracker.error(str(exc))
        raise


async def run_project_extraction_trigger_after_commit(
    db: AsyncSession,
    *,
    project_id: str,
    user_id: str,
    trigger_source: str,
    force: bool = False,
    extractor: ExtractionCallable | Callable[..., RawExtractionOutput] | None = None,
    enabled: bool | None = None,
    supersede_prior: bool = True,
) -> list[ExtractionTriggerResult]:
    """Best-effort project-wide automatic trigger after an import commit."""

    if enabled is None:
        enabled = bool(app_settings.EXTRACTION_PIPELINE_ENABLED)
    if not enabled:
        return []
    try:
        results = await db.run_sync(
            lambda session: ExtractionTriggerService(session).trigger_project(
                project_id=project_id,
                user_id=user_id,
                trigger_source=trigger_source,
                force=force,
                extractor=extractor,
                enabled=True,
                supersede_prior=supersede_prior,
            )
        )
        await db.commit()
        return results
    except Exception as exc:
        await db.rollback()
        logger.warning("项目正文抽取触发失败，已保留已落库导入内容: %s", exc, exc_info=True)
        return []


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
