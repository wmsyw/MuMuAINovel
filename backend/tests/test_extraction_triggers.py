import asyncio
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import Base
from app.models import Chapter, Character, ExtractionCandidate, ExtractionRun, Project
from app.services.character_state_update_service import CharacterStateUpdateService
from app.services.extraction_service import ExtractionContext, ExtractionTriggerService


RunSyncT = TypeVar("RunSyncT")


class ExecuteResultProtocol(Protocol):
    def scalar_one_or_none(self) -> object | None: ...
    def scalars(self) -> Any: ...


class AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return cast(ExecuteResultProtocol, self.session.execute(*args, **kwargs))

    async def run_sync(self, fn: Callable[[Session], RunSyncT]) -> RunSyncT:
        return fn(self.session)

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()


class FakeExtractor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0
        self.contexts: list[ExtractionContext] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.contexts.append(kwargs["context"])
        if self.fail:
            raise RuntimeError("boom after persistence")
        chapter = kwargs["chapter"]
        content = chapter.content or ""
        evidence = content[: max(1, min(3, len(content)))]
        return {
            "candidates": [
                {
                    "candidate_type": "character_state",
                    "character": "沈砚",
                    "state": "发现线索",
                    "confidence": 0.91,
                    "evidence_text": evidence,
                    "source": {
                        "chapter_id": chapter.id,
                        "chapter": chapter.chapter_number,
                        "order": int(chapter.sub_index or 1),
                        "offset_start": 0,
                        "offset_end": len(evidence),
                    },
                    "payload": {"state": "发现线索"},
                }
            ]
        }


def _count(session: Session, model: type[object]) -> int:
    return int(session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one())


def _seed(session: Session, *, chapter_count: int = 3) -> None:
    session.add(Project(id="project-triggers", user_id="user-triggers", title="触发器测试", current_words=0))
    session.add(Character(id="char-shen", project_id="project-triggers", name="沈砚", current_state="旧状态"))
    session.add(Character(id="char-lin", project_id="project-triggers", name="林青岚"))
    for number in range(1, chapter_count + 1):
        session.add(
            Chapter(
                id=f"chapter-trigger-{number}",
                project_id="project-triggers",
                chapter_number=number,
                title=f"第{number}章",
                content=f"沈砚在第{number}章发现巡星司线索。林青岚保持戒心。",
                word_count=20,
                sub_index=number,
                status="completed",
            )
        )
    session.commit()


def _memory_session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    connection = engine.connect()
    return Session(bind=connection)


def test_chapter_save_trigger_dedupes_unchanged_content_and_supersedes_replaced_evidence() -> None:
    session = _memory_session()
    _seed(session, chapter_count=1)
    fake = FakeExtractor()
    service = ExtractionTriggerService(session)

    first = service.trigger_chapter(
        project_id="project-triggers",
        chapter_id="chapter-trigger-1",
        user_id="user-triggers",
        trigger_source="chapter_save",
        extractor=fake,
        enabled=True,
    )
    second = service.trigger_chapter(
        project_id="project-triggers",
        chapter_id="chapter-trigger-1",
        user_id="user-triggers",
        trigger_source="chapter_save",
        extractor=fake,
        enabled=True,
    )
    session.flush()

    assert first is not None and second is not None
    assert first.run_id == second.run_id
    assert second.reused_existing_run is True
    assert fake.calls == 1
    assert _count(session, ExtractionRun) == 1
    assert _count(session, ExtractionCandidate) == 1

    chapter = session.get(Chapter, "chapter-trigger-1")
    assert chapter is not None
    chapter.content = "沈砚重写后的正文证据覆盖旧证据。"
    chapter.word_count = len(chapter.content)
    session.commit()

    replaced = service.trigger_chapter(
        project_id="project-triggers",
        chapter_id="chapter-trigger-1",
        user_id="user-triggers",
        trigger_source="chapter_save",
        extractor=fake,
        enabled=True,
    )
    session.flush()

    assert replaced is not None
    assert replaced.run_id != first.run_id
    assert fake.calls == 2
    statuses = session.execute(
        sa.select(ExtractionCandidate.status).order_by(ExtractionCandidate.created_at.asc(), ExtractionCandidate.id.asc())
    ).scalars().all()
    assert sorted(str(status) for status in statuses) == ["pending", "superseded"]


def test_generated_chapter_extraction_failure_preserves_persisted_text_and_failed_run_status() -> None:
    session = _memory_session()
    _seed(session, chapter_count=1)
    chapter = session.get(Chapter, "chapter-trigger-1")
    assert chapter is not None
    chapter.content = "生成成功后已经落库的正文。"
    session.commit()

    result = ExtractionTriggerService(session).trigger_chapter(
        project_id="project-triggers",
        chapter_id=chapter.id,
        user_id="user-triggers",
        trigger_source="chapter_generation",
        extractor=FakeExtractor(fail=True),
        enabled=True,
    )
    session.flush()

    assert result is not None
    run = session.get(ExtractionRun, result.run_id)
    assert run is not None
    assert run.status == "failed"
    assert "boom after persistence" in str(run.error_message)
    assert session.get(Chapter, chapter.id).content == "生成成功后已经落库的正文。"
    assert _count(session, ExtractionCandidate) == 0


def test_txt_import_apply_triggers_one_run_per_imported_chapter_after_commit() -> None:
    session = _memory_session()
    _seed(session, chapter_count=2)
    fake = FakeExtractor()

    results = ExtractionTriggerService(session).trigger_project(
        project_id="project-triggers",
        user_id="user-triggers",
        trigger_source="book_import",
        force=False,
        extractor=fake,
        enabled=True,
        supersede_prior=True,
    )
    session.flush()

    assert len(results) == 2
    assert {result.status for result in results} == {"completed"}
    assert fake.calls == 2
    assert _count(session, ExtractionRun) == 2
    assert _count(session, ExtractionCandidate) == 2
    assert {context.trigger_source for context in fake.contexts} == {"book_import"}


def test_disabled_automatic_trigger_skips_extraction() -> None:
    session = _memory_session()
    _seed(session, chapter_count=1)
    fake = FakeExtractor()

    result = ExtractionTriggerService(session).trigger_chapter(
        project_id="project-triggers",
        chapter_id="chapter-trigger-1",
        user_id="user-triggers",
        trigger_source="chapter_save",
        extractor=fake,
        enabled=False,
    )

    assert result is None
    assert fake.calls == 0
    assert _count(session, ExtractionRun) == 0


def test_manual_project_chapter_and_range_reextract_create_forced_runs_without_canonical_deletes() -> None:
    session = _memory_session()
    _seed(session, chapter_count=3)
    fake = FakeExtractor()
    service = ExtractionTriggerService(session)

    project_runs = service.trigger_project(
        project_id="project-triggers",
        user_id="user-triggers",
        extractor=fake,
        enabled=True,
        force=True,
        trigger_source="manual_project",
    )
    chapter_run = service.trigger_chapter(
        project_id="project-triggers",
        chapter_id="chapter-trigger-2",
        user_id="user-triggers",
        extractor=fake,
        enabled=True,
        force=True,
        trigger_source="manual_chapter",
        supersede_prior=False,
    )
    range_runs = service.trigger_chapter_range(
        project_id="project-triggers",
        user_id="user-triggers",
        start_chapter_number=2,
        end_chapter_number=3,
        extractor=fake,
        enabled=True,
        force=True,
        trigger_source="manual_range",
    )
    session.flush()

    assert len(project_runs) == 3
    assert chapter_run is not None
    assert len(range_runs) == 2
    assert _count(session, ExtractionRun) == 6
    assert _count(session, Character) == 2
    assert {str(row) for row in session.execute(sa.select(ExtractionRun.trigger_source)).scalars().all()} == {
        "manual_project",
        "manual_chapter",
        "manual_range",
    }


def test_character_state_update_service_stages_candidates_when_pipeline_enabled(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "EXTRACTION_PIPELINE_ENABLED", True)
    session = _memory_session()
    _seed(session, chapter_count=1)
    adapter = AsyncSessionAdapter(session)

    result = asyncio.run(
        CharacterStateUpdateService.update_from_analysis(
            db=cast(Any, adapter),
            project_id="project-triggers",
            chapter_id="chapter-trigger-1",
            chapter_number=1,
            character_states=[
                {
                    "character_name": "沈砚",
                    "state_before": "旧状态",
                    "state_after": "保持戒心",
                    "psychological_change": "保持戒心",
                    "relationship_changes": {"林青岚": "互相试探"},
                    "organization_changes": [
                        {"organization_name": "巡星司", "change_type": "joined", "description": "加入巡星司"}
                    ],
                },
                {
                    "character_name": "林青岚",
                    "survival_status": "missing",
                    "key_event": "林青岚保持戒心",
                },
            ],
        )
    )

    session.refresh(session.get(Character, "char-shen"))
    assert session.get(Character, "char-shen").current_state == "旧状态"
    assert result["state_updated_count"] == 2
    assert result["relationship_created_count"] == 1
    assert result["org_updated_count"] == 1
    candidates = session.execute(sa.select(ExtractionCandidate)).scalars().all()
    assert {candidate.candidate_type for candidate in candidates} == {"character_state", "relationship", "organization_affiliation"}
    survival = next(candidate for candidate in candidates if candidate.payload.get("survival_status") == "missing")
    assert survival.confidence == 0.98
    assert survival.payload["auto_accept"] is True
