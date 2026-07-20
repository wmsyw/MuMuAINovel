from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportGeneralTypeIssues=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

import json
from typing import Any
from time import perf_counter

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chapter, Character, EntityRelationship, ExtractionCandidate, ExtractionRun, Project
from app.services.extraction_service import run_automatic_chapter_extraction_task


CONTENT = "李云飞与王虎结为好友。"


class FakeAIService:
    async def generate_text(self, **_: Any) -> dict[str, str]:
        candidates = {
            "candidates": [
                {
                    "candidate_type": "character",
                    "name": "李云飞",
                    "confidence": 0.99,
                    "evidence_text": "李云飞",
                    "source": {"chapter": 1, "order": 1, "offset_start": 0, "offset_end": 3},
                    "payload": {},
                },
                {
                    "candidate_type": "character",
                    "name": "王虎",
                    "confidence": 0.99,
                    "evidence_text": "王虎",
                    "source": {"chapter": 1, "order": 1, "offset_start": 4, "offset_end": 6},
                    "payload": {},
                },
                {
                    "candidate_type": "relationship",
                    "name": "好友",
                    "confidence": 0.98,
                    "evidence_text": CONTENT,
                    "source": {"chapter": 1, "order": 1, "offset_start": 0, "offset_end": len(CONTENT)},
                    "payload": {
                        "participants": ["李云飞", "王虎"],
                        "relationship_name": "好友",
                        "strength": 80,
                    },
                },
            ]
        }
        return {"content": json.dumps(candidates, ensure_ascii=False)}


class FailingAIService:
    async def generate_text(self, **_: Any) -> dict[str, str]:
        raise RuntimeError("provider unavailable")


class RecordingTracker:
    completed: list[dict[str, Any]] = []
    errors: list[str] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def start(self, *_: Any, **__: Any) -> None:
        pass

    async def loading(self, *_: Any, **__: Any) -> None:
        pass

    async def generating(self, *_: Any, **__: Any) -> None:
        pass

    async def parsing(self, *_: Any, **__: Any) -> None:
        pass

    async def saving(self, *_: Any, **__: Any) -> None:
        pass

    async def complete(self, message: str, *, result: dict[str, Any] | None = None) -> None:
        self.completed.append({"message": message, "result": result})

    async def error(self, message: str) -> None:
        self.errors.append(message)


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as db:
        db.add(Project(id="project-auto-extract", user_id="user-auto-extract", title="自动抽取测试", current_words=len(CONTENT)))
        db.add_all(
            [
                Character(id="character-li", project_id="project-auto-extract", name="李云飞"),
                Character(id="character-wang", project_id="project-auto-extract", name="王虎"),
                Chapter(
                    id="chapter-auto-extract",
                    project_id="project-auto-extract",
                    chapter_number=1,
                    sub_index=1,
                    title="初识",
                    content=CONTENT,
                    word_count=len(CONTENT),
                    status="completed",
                ),
            ]
        )
        await db.commit()


def _patch_task_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    ai_service: FakeAIService | FailingAIService,
) -> None:
    import app.api.settings as settings_api
    import app.config as app_config
    import app.database as database
    import app.services.background_task_service as background_tasks

    async def fake_get_engine(_: str):
        return session_factory.kw["bind"]

    async def fake_get_ai_service(_: str, __: AsyncSession):
        return ai_service

    RecordingTracker.completed.clear()
    RecordingTracker.errors.clear()
    monkeypatch.setattr(database, "get_engine", fake_get_engine)
    monkeypatch.setattr(settings_api, "get_user_ai_service_from_db", fake_get_ai_service)
    monkeypatch.setattr(background_tasks, "TaskProgressTracker", RecordingTracker)
    monkeypatch.setattr(app_config.settings, "EXTRACTION_PIPELINE_ENABLED", True)


@pytest.mark.asyncio
async def test_automatic_chapter_task_extracts_merges_and_creates_relationship(
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(async_db_session)
    _patch_task_dependencies(monkeypatch, async_db_session, FakeAIService())

    await run_automatic_chapter_extraction_task(
        "task-auto-extract",
        "user-auto-extract",
        "project-auto-extract",
        "chapter-auto-extract",
    )

    async with async_db_session() as db:
        candidates = (await db.execute(select(ExtractionCandidate))).scalars().all()
        relationships = (await db.execute(select(EntityRelationship))).scalars().all()
        runs = (await db.execute(select(ExtractionRun))).scalars().all()

    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert len(candidates) == 3
    assert {candidate.status for candidate in candidates} == {"merged"}
    assert len(relationships) == 1
    assert relationships[0].relationship_name == "好友"
    assert RecordingTracker.errors == []
    assert RecordingTracker.completed[0]["result"] == {
        "project_id": "project-auto-extract",
        "chapter_id": "chapter-auto-extract",
        "chapter_title": "初识",
        "run_id": runs[0].id,
        "candidate_count": 3,
        "pending_count": 0,
        "counts": {"character": 2, "relationship": 1},
        "similarity": {"staged": 2, "merged": 2, "ambiguous": 0},
        "accepted_relationships": 1,
    }


@pytest.mark.asyncio
async def test_automatic_chapter_task_reports_provider_failure_without_partial_run(
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(async_db_session)
    _patch_task_dependencies(monkeypatch, async_db_session, FailingAIService())

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await run_automatic_chapter_extraction_task(
            "task-auto-extract-failed",
            "user-auto-extract",
            "project-auto-extract",
            "chapter-auto-extract",
        )

    async with async_db_session() as db:
        runs = (await db.execute(select(ExtractionRun))).scalars().all()

    assert runs == []
    assert RecordingTracker.completed == []
    assert RecordingTracker.errors == ["provider unavailable"]


@pytest.mark.asyncio
async def test_automatic_extraction_of_ten_thousand_characters_meets_budget(
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(async_db_session)
    async with async_db_session() as db:
        chapter = await db.get(Chapter, "chapter-auto-extract")
        assert chapter is not None
        chapter.content = CONTENT + ("长" * 10_000)
        chapter.word_count = len(chapter.content)
        await db.commit()

    _patch_task_dependencies(monkeypatch, async_db_session, FakeAIService())
    started_at = perf_counter()
    await run_automatic_chapter_extraction_task(
        "task-auto-extract-large",
        "user-auto-extract",
        "project-auto-extract",
        "chapter-auto-extract",
    )
    elapsed = perf_counter() - started_at

    assert RecordingTracker.completed[0]["result"]["candidate_count"] == 3
    assert elapsed < 15, f"10k chapter extraction exceeded 15s budget: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_automatic_chapter_task_skips_ai_when_pipeline_disabled(
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(async_db_session)
    _patch_task_dependencies(monkeypatch, async_db_session, FakeAIService())
    import app.config as app_config

    monkeypatch.setattr(app_config.settings, "EXTRACTION_PIPELINE_ENABLED", False)
    await run_automatic_chapter_extraction_task(
        "task-auto-extract-disabled",
        "user-auto-extract",
        "project-auto-extract",
        "chapter-auto-extract",
    )

    async with async_db_session() as db:
        runs = (await db.execute(select(ExtractionRun))).scalars().all()
    assert runs == []
    assert RecordingTracker.completed == []
    assert RecordingTracker.errors == []
