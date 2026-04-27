import asyncio
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Character, CharacterRelationship, Chapter, EntityProvenance, EntityRelationship, ExtractionCandidate, ExtractionRun, Project, RelationshipTimelineEvent
from app.schemas.relationship import CharacterRelationshipResponse
from app.api.relationships import _load_relationship_enrichment, _relationship_base_payload
from app.services.chapter_fact_sync_service import ChapterFactSyncService
from app.services.relationship_merge_service import RelationshipMergeService


PROJECT_ID = "project-relationship-convergence"
USER_ID = "user-relationship-convergence"
CHAPTER_ID = "chapter-relationship-convergence"


class AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.session.execute(*args, **kwargs)

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.session.get(*args, **kwargs)

    def add(self, value: Any) -> None:
        self.session.add(value)

    async def flush(self) -> None:
        self.session.flush()

    async def commit(self) -> None:
        self.session.commit()

    async def refresh(self, value: Any) -> None:
        self.session.refresh(value)


def _session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    connection = engine.connect()
    Base.metadata.create_all(connection)
    return Session(bind=connection)


def _seed(session: Session) -> None:
    session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="关系收敛"))
    session.add(Chapter(id=CHAPTER_ID, project_id=PROJECT_ID, chapter_number=1, title="第一章", content="沈砚与林青岚互为盟友。", sub_index=1))
    session.add_all([
        Character(id="char-shen", project_id=PROJECT_ID, name="沈砚"),
        Character(id="char-lin", project_id=PROJECT_ID, name="林青岚"),
    ])
    session.commit()


def _count(session: Session, model: type[object]) -> int:
    return int(session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one())


def _stub_memory_service(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("app.services.memory_service")
    service = SimpleNamespace(
        delete_chapter_memories=lambda **_: None,
        batch_add_memories=lambda **_: 0,
        run_state_cleanup=lambda **_: {},
    )
    setattr(module, "memory_service", service)
    monkeypatch.setitem(sys.modules, "app.services.memory_service", module)

    email_module = types.ModuleType("app.services.email_service")
    setattr(email_module, "email_service", SimpleNamespace(send_mail=lambda **_: None))
    monkeypatch.setitem(sys.modules, "app.services.email_service", email_module)


def test_manual_relationship_merge_writes_entity_relationship_only_and_api_schema_stays_compatible() -> None:
    session = _session()
    _seed(session)

    async def run_merge() -> EntityRelationship:
        result = await RelationshipMergeService(AsyncSessionAdapter(session)).merge_character_relationship(
            project_id=PROJECT_ID,
            character_from_id="char-shen",
            character_to_id="char-lin",
            relationship_name="盟友",
            intimacy_level=75,
            status="active",
            description="并肩作战",
            source="manual",
            source_chapter_id=CHAPTER_ID,
            evidence_excerpt="沈砚与林青岚互为盟友",
            confidence=1.0,
            allow_conflict_apply=True,
        )
        assert result.relationship is not None
        return result.relationship

    relationship = asyncio.run(run_merge())
    session.commit()
    session.refresh(relationship)

    assert _count(session, CharacterRelationship) == 0
    assert _count(session, EntityRelationship) == 1
    payload = TypeAdapter(CharacterRelationshipResponse).validate_python(relationship).model_dump()
    assert payload["character_from_id"] == "char-shen"
    assert payload["character_to_id"] == "char-lin"
    assert payload["relationship_name"] == "盟友"
    assert payload["source"] == "manual"


def test_relationship_conflict_is_staged_as_pending_candidate_with_merge_evidence() -> None:
    session = _session()
    _seed(session)
    session.add(EntityRelationship(
        id="rel-existing",
        project_id=PROJECT_ID,
        from_entity_type="character",
        from_entity_id="char-shen",
        to_entity_type="character",
        to_entity_id="char-lin",
        relationship_name="盟友",
        status="active",
        source="manual",
    ))
    session.commit()

    async def run_conflict() -> None:
        result = await RelationshipMergeService(AsyncSessionAdapter(session)).merge_character_relationship(
            project_id=PROJECT_ID,
            character_from_id="char-shen",
            character_to_id="char-lin",
            relationship_name="仇敌",
            status="active",
            source="analysis",
            source_chapter_id=CHAPTER_ID,
            evidence_excerpt="二人公开决裂",
            confidence=0.96,
        )
        assert result.relationship is not None
        assert result.candidate is not None
        assert result.decision == "pending"

    asyncio.run(run_conflict())
    session.commit()

    relationship = session.get(EntityRelationship, "rel-existing")
    assert relationship is not None
    assert relationship.relationship_name == "盟友"
    candidate = session.execute(sa.select(ExtractionCandidate)).scalar_one()
    assert candidate.status == "pending"
    assert candidate.review_required_reason == "relationship_name_conflict"
    assert candidate.payload["old_value"]["relationship_name"] == "盟友"
    assert candidate.payload["new_value"]["relationship_name"] == "仇敌"
    assert candidate.payload["evidence_excerpt"] == "二人公开决裂"
    assert candidate.payload["merge_decision"] == "pending"
    assert _count(session, ExtractionRun) == 1


def test_relationship_api_contract_exposes_provenance_history_and_pending_count() -> None:
    session = _session()
    _seed(session)
    relationship = EntityRelationship(
        id="rel-provenance",
        project_id=PROJECT_ID,
        from_entity_type="character",
        from_entity_id="char-shen",
        to_entity_type="character",
        to_entity_id="char-lin",
        relationship_name="盟友",
        intimacy_level=82,
        status="active",
        description="并肩守城",
        source="extraction",
    )
    run = ExtractionRun(
        id="run-provenance",
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        trigger_source="chapter_save",
        pipeline_version="chapter-fact-sync-v1",
        schema_version="chapter-fact-sync-v1:relationship",
        prompt_hash="prompt-provenance",
        content_hash="content-provenance",
        status="completed",
    )
    pending = ExtractionCandidate(
        id="candidate-pending-conflict",
        run_id=run.id,
        project_id=PROJECT_ID,
        user_id=USER_ID,
        source_chapter_id=CHAPTER_ID,
        source_chapter_start_id=CHAPTER_ID,
        source_chapter_end_id=CHAPTER_ID,
        candidate_type="relationship",
        trigger_type="chapter_save",
        source_hash="pending-source",
        display_name="仇敌",
        normalized_name="仇敌",
        canonical_target_type="relationship",
        canonical_target_id=relationship.id,
        status="pending",
        confidence=0.62,
        evidence_text="低置信度称二人反目",
        source_start_offset=4,
        source_end_offset=13,
        source_chapter_number=1,
        source_chapter_order=1,
        payload={
            "character_from_id": "char-shen",
            "character_to_id": "char-lin",
            "relationship_name": "仇敌",
            "old_value": {"relationship_name": "盟友"},
            "new_value": {"relationship_name": "仇敌"},
        },
        raw_payload={},
        review_required_reason="low_confidence",
    )
    provenance = EntityProvenance(
        id="prov-relationship",
        project_id=PROJECT_ID,
        entity_type="relationship",
        entity_id=relationship.id,
        source_type="extraction_candidate",
        source_id=pending.id,
        run_id=run.id,
        candidate_id=pending.id,
        chapter_id=CHAPTER_ID,
        claim_type="relationship_claim",
        claim_payload={"relationship_name": "盟友"},
        evidence_text="沈砚与林青岚在城墙上立誓结盟",
        source_start=0,
        source_end=16,
        confidence=0.91,
        status="active",
        created_by=USER_ID,
    )
    history = RelationshipTimelineEvent(
        id="history-relationship",
        project_id=PROJECT_ID,
        relationship_id=relationship.id,
        character_id="char-shen",
        related_character_id="char-lin",
        event_type="relationship",
        event_status="active",
        relationship_name="盟友",
        source_chapter_id=CHAPTER_ID,
        source_chapter_order=1,
        valid_from_chapter_id=CHAPTER_ID,
        valid_from_chapter_order=1,
        source_start_offset=0,
        source_end_offset=16,
        evidence_text="沈砚与林青岚在城墙上立誓结盟",
        confidence=0.91,
        provenance_id=provenance.id,
    )
    session.add_all([relationship, run, pending, provenance, history])
    session.commit()
    session.refresh(relationship)

    enrichment = asyncio.run(_load_relationship_enrichment(AsyncSessionAdapter(session), [relationship]))
    payload = _relationship_base_payload(relationship)
    payload.update(enrichment[relationship.id])
    response = TypeAdapter(CharacterRelationshipResponse).validate_python(payload).model_dump()

    assert response["source_chapter_id"] == CHAPTER_ID
    assert response["source_chapter_order"] == 1
    assert response["evidence_text"] == "沈砚与林青岚在城墙上立誓结盟"
    assert response["confidence"] == 0.91
    assert response["pending_candidate_count"] == 1
    assert response["provenance"][0]["claim_type"] == "relationship_claim"
    assert response["history"][0]["relationship_name"] == "盟友"


def test_manual_and_generated_chapter_saves_schedule_chapter_fact_sync_non_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_memory_service(monkeypatch)
    from app.api import chapters as chapters_api

    scheduled: list[Any] = []

    def fake_create_task(coro: Any) -> SimpleNamespace:
        scheduled.append(coro)
        coro.close()
        return SimpleNamespace(done=lambda: False)

    monkeypatch.setattr(chapters_api.asyncio, "create_task", fake_create_task)
    manual = chapters_api._schedule_chapter_fact_sync_fire_and_forget(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content="沈砚与林青岚互为盟友。",
        source="chapter_save",
        source_metadata={"operation": "update_chapter"},
    )
    empty = chapters_api._schedule_chapter_fact_sync_fire_and_forget(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content="  ",
        source="chapter_save",
    )
    generated = chapters_api._schedule_chapter_fact_sync_fire_and_forget(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content="生成正文保存后调度。",
        source="chapter_generation",
        source_metadata={"operation": "generate_chapter_content_stream"},
    )

    assert manual is not None
    assert empty is None
    assert generated is not None
    assert len(scheduled) == 2


def test_apply_partial_regenerate_schedules_chapter_fact_sync_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_memory_service(monkeypatch)
    from app.api import chapters as chapters_api

    session = _session()
    _seed(session)
    scheduled: list[dict[str, Any]] = []

    async def fake_verify_project_access(project_id: str, user_id: str, db: Any) -> Project:
        assert project_id == PROJECT_ID
        assert user_id == USER_ID
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        return project

    def fake_schedule(**kwargs: Any) -> None:
        scheduled.append(kwargs)

    monkeypatch.setattr(chapters_api, "verify_project_access", fake_verify_project_access)
    monkeypatch.setattr(chapters_api, "_schedule_chapter_fact_sync_fire_and_forget", fake_schedule)

    response = asyncio.run(chapters_api.apply_partial_regenerate(
        CHAPTER_ID,
        SimpleNamespace(state=SimpleNamespace(user_id=USER_ID)),
        {"new_text": "结成生死盟友", "start_position": 3, "end_position": 9},
        AsyncSessionAdapter(session),
    ))

    chapter = session.get(Chapter, CHAPTER_ID)
    assert chapter is not None
    assert chapter.content == "沈砚与结成生死盟友友。"
    assert response == {
        "success": True,
        "chapter_id": CHAPTER_ID,
        "word_count": len(chapter.content),
        "old_word_count": 0,
        "message": "局部重写已应用",
    }
    assert scheduled == [{
        "user_id": USER_ID,
        "project_id": PROJECT_ID,
        "chapter_id": CHAPTER_ID,
        "content": chapter.content,
        "source": "chapter_partial_regenerate",
        "source_metadata": {
            "operation": "apply_partial_regenerate",
            "start_position": 3,
            "end_position": 9,
            "old_word_count": 0,
            "new_word_count": len(chapter.content),
            "replacement_word_count": len("结成生死盟友"),
        },
    }]


def test_memories_analysis_path_schedules_shared_sync_without_direct_character_relationship_write(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_memory_service(monkeypatch)
    from app.api import memories as memories_api

    scheduled: list[Any] = []

    def fake_create_task(coro: Any) -> SimpleNamespace:
        scheduled.append(coro)
        coro.close()
        return SimpleNamespace(done=lambda: False)

    monkeypatch.setattr(memories_api.asyncio, "create_task", fake_create_task)
    memories_api._schedule_memory_fact_sync(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content="记忆分析后的正文。",
        chapter_number=1,
    )

    source = Path(memories_api.__file__).read_text(encoding="utf-8")
    assert len(scheduled) == 1
    assert "CharacterStateUpdateService.update_from_analysis" not in source
    assert "ChapterFactSyncService" in source


def test_generated_content_sync_is_idempotent_for_runs_and_history() -> None:
    session = _session()
    _seed(session)
    service = ChapterFactSyncService(session)
    content = "同一段生成正文反复保存。"

    first = service.schedule_for_chapter(project_id=PROJECT_ID, chapter_id=CHAPTER_ID, content=content, source="chapter_generation")
    second = service.schedule_for_chapter(project_id=PROJECT_ID, chapter_id=CHAPTER_ID, content=content, source="chapter_generation")
    session.commit()

    assert [run.id for run in first] == [run.id for run in second]
    assert _count(session, ExtractionRun) == 2
    assert _count(session, EntityRelationship) == 0


def test_partial_regenerate_sync_is_idempotent_for_relationship_and_goldfinger_runs() -> None:
    session = _session()
    _seed(session)
    service = ChapterFactSyncService(session)
    content = "局部重写应用后的正文，沈砚与林青岚仍互为盟友，天命系统继续苏醒。"

    first = service.schedule_for_chapter(
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content=content,
        source="chapter_partial_regenerate",
        source_metadata={"operation": "apply_partial_regenerate"},
    )
    second = service.schedule_for_chapter(
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content=content,
        source="chapter_partial_regenerate",
        source_metadata={"operation": "apply_partial_regenerate"},
    )
    session.commit()

    assert [run.id for run in first] == [run.id for run in second]
    assert _count(session, ExtractionRun) == 2
    assert {run.run_metadata["entity_type"] for run in first} == {"relationship", "goldfinger"}
    assert {run.trigger_source for run in first} == {"chapter_partial_regenerate"}


def test_no_application_code_directly_constructs_character_relationship_writes() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in (backend_root / "app").rglob("*.py"):
        if path.name == "relationship.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "CharacterRelationship(" in source or "delete(CharacterRelationship)" in source:
            offenders.append(str(path.relative_to(backend_root)))

    assert offenders == []
