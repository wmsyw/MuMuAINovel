import socket
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Career,
    Chapter,
    Character,
    EntityProvenance,
    ExtractionCandidate,
    ExtractionRun,
    OrganizationEntity,
    Project,
    RelationshipTimelineEvent,
    WorldSettingResult,
)
from app.services.extraction_service import (
    EXTRACTION_PIPELINE_VERSION,
    EXTRACTION_SCHEMA_VERSION,
    ExtractionContext,
    extract_chapter_candidates,
)

from .fixture_schema import load_golden_fixture


class FakeExtractor:
    def __init__(self, output: Any) -> None:
        self.output = output
        self.calls = 0
        self.contexts: list[ExtractionContext] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls += 1
        self.contexts.append(kwargs["context"])
        assert "schema_version" in kwargs["schema"]
        assert kwargs["chapter"].content
        return self.output


def _count(session: Session, model: type[object]) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def _seed_project_with_golden_chapters(session: Session) -> dict[int, Chapter]:
    fixture = load_golden_fixture()
    project = Project(
        id="project-extraction",
        user_id="user-extraction",
        title="雨夜星图",
        description=fixture["description"],
        genre="悬疑仙侠",
    )
    session.add(project)

    chapters_by_number: dict[int, Chapter] = {}
    for chapter_data in fixture["chapters"]:
        chapter = Chapter(
            id=f"chapter-{chapter_data['chapter']}",
            project_id=project.id,
            chapter_number=chapter_data["chapter"],
            title=chapter_data["title"],
            content=chapter_data["content"],
            sub_index=chapter_data["order"],
            status="published",
        )
        session.add(chapter)
        chapters_by_number[chapter.chapter_number] = chapter
    session.flush()
    return chapters_by_number


def _fake_candidate_payload(chapter: Chapter) -> dict[str, Any]:
    fixture = load_golden_fixture()
    expected = fixture["expected"]
    affiliation = expected["organization_affiliations"][0]
    profession = expected["profession_changes"][1]
    relationship = expected["relationships"][1]
    world_fact = expected["world_facts"][0]

    assert affiliation["source"]["chapter"] == chapter.chapter_number
    assert profession["source"]["chapter"] == chapter.chapter_number
    assert relationship["source"]["chapter"] == chapter.chapter_number
    assert world_fact["source"]["chapter"] == chapter.chapter_number

    def source(assertion: dict[str, Any]) -> dict[str, Any]:
        raw_source = assertion["source"]
        return {
            "chapter_id": chapter.id,
            "chapter": raw_source["chapter"],
            "order": raw_source["order"],
            "offset_start": raw_source["offset_start"],
            "offset_end": raw_source["offset_end"],
        }

    return {
        "candidates": [
            {
                "candidate_type": "character",
                "canonical_name": "林青岚",
                "aliases": ["青岚"],
                "confidence": affiliation["confidence"],
                "evidence_text": affiliation["evidence_text"],
                "source": source(affiliation),
                "story_time_label": "三个月后",
                "payload": {"role": "巡星司外勤"},
            },
            {
                "candidate_type": "organization",
                "name": "巡星司",
                "confidence": affiliation["confidence"],
                "evidence_text": affiliation["evidence_text"],
                "source": source(affiliation),
                "payload": {"organization_type": "官署"},
            },
            {
                "candidate_type": "profession",
                "profession": profession["profession"],
                "confidence": profession["confidence"],
                "evidence_text": profession["evidence_text"],
                "source": source(profession),
                "payload": {"profession": profession["profession"]},
            },
            {
                "candidate_type": "relationship",
                "relationship": relationship["relationship"],
                "confidence": relationship["confidence"],
                "evidence_text": relationship["evidence_text"],
                "source": source(relationship),
                "payload": {
                    "participants": relationship["participants"],
                    "state": relationship["state"],
                },
            },
            {
                "candidate_type": "organization_affiliation",
                "character": affiliation["character"],
                "current_organization": affiliation["current_organization"],
                "confidence": affiliation["confidence"],
                "evidence_text": affiliation["evidence_text"],
                "source": source(affiliation),
                "story_time_label": "三个月后",
                "payload": {
                    "previous_organization": affiliation["previous_organization"],
                    "current_organization": affiliation["current_organization"],
                    "change": affiliation["change"],
                },
            },
            {
                "candidate_type": "profession_assignment",
                "character": profession["character"],
                "profession": profession["profession"],
                "confidence": profession["confidence"],
                "evidence_text": profession["evidence_text"],
                "source": source(profession),
                "payload": {"state": profession["state"]},
            },
            {
                "candidate_type": "world_fact",
                "subject": world_fact["subject"],
                "confidence": world_fact["confidence"],
                "evidence_text": world_fact["evidence_text"],
                "source": source(world_fact),
                "payload": {
                    "fact_type": world_fact["fact_type"],
                    "fact": world_fact["fact"],
                },
            },
            {
                "candidate_type": "character_state",
                "character": "林青岚",
                "state": "与沈砚互不信任",
                "confidence": relationship["confidence"],
                "evidence_text": relationship["evidence_text"],
                "source": source(relationship),
                "payload": {"related_character": "沈砚", "state": "互不信任的临时盟友"},
            },
        ]
    }


def test_golden_chapter_extraction_stages_only_pending_candidates(monkeypatch) -> None:
    network_attempts: list[tuple[object, object]] = []

    def fail_on_network(self, address):
        network_attempts.append((self, address))
        raise AssertionError(f"extraction test attempted network access: {address}")

    monkeypatch.setattr(socket.socket, "connect", fail_on_network)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            chapter = _seed_project_with_golden_chapters(session)[2]
            fake = FakeExtractor(_fake_candidate_payload(chapter))

            run = extract_chapter_candidates(
                session,
                project_id="project-extraction",
                chapter_id=chapter.id,
                user_id="user-extraction",
                extractor=fake,
                trigger_source="manual",
                provider="fake-provider",
                model="fake-model",
                reasoning_intensity="off",
                source_metadata={"test": "golden"},
            )
            session.flush()

            assert fake.calls == 1
            assert network_attempts == []
            assert _count(session, ExtractionRun) == 1
            assert run.status == "completed"
            assert run.project_id == "project-extraction"
            assert run.chapter_id == chapter.id
            assert run.pipeline_version == EXTRACTION_PIPELINE_VERSION
            assert run.schema_version == EXTRACTION_SCHEMA_VERSION
            assert run.content_hash
            assert run.prompt_hash
            assert run.provider == "fake-provider"
            assert run.model == "fake-model"
            assert run.reasoning_intensity == "off"
            assert run.run_metadata["source_metadata"] == {"test": "golden"}

            candidates = session.execute(
                sa.select(ExtractionCandidate).where(ExtractionCandidate.run_id == run.id)
            ).scalars().all()
            assert len(candidates) == 8
            assert {candidate.candidate_type for candidate in candidates} == {
                "character",
                "organization",
                "profession",
                "relationship",
                "organization_affiliation",
                "profession_assignment",
                "world_fact",
                "character_state",
            }
            assert all(candidate.status == "pending" for candidate in candidates)
            assert all(candidate.project_id == "project-extraction" for candidate in candidates)
            assert all(candidate.user_id == "user-extraction" for candidate in candidates)
            assert all(candidate.source_chapter_id == chapter.id for candidate in candidates)
            assert all(candidate.source_chapter_start_id == chapter.id for candidate in candidates)
            assert all(candidate.source_chapter_end_id == chapter.id for candidate in candidates)
            assert all(candidate.source_chapter_number == 2 for candidate in candidates)
            assert all(candidate.source_chapter_order == 2 for candidate in candidates)
            assert all(candidate.provider == "fake-provider" for candidate in candidates)
            assert all(candidate.model == "fake-model" for candidate in candidates)
            assert all(candidate.reasoning_intensity == "off" for candidate in candidates)

            for candidate in candidates:
                assert 0 <= candidate.confidence <= 1
                assert chapter.content[candidate.source_start_offset:candidate.source_end_offset] == candidate.evidence_text
                assert candidate.raw_payload["candidate_type"] == candidate.candidate_type
                assert candidate.payload["source"]["chapter_id"] == chapter.id
                assert candidate.payload["source"]["offset_start"] == candidate.source_start_offset
                assert candidate.payload["source"]["offset_end"] == candidate.source_end_offset

            character = next(candidate for candidate in candidates if candidate.candidate_type == "character")
            assert character.display_name == "林青岚"
            assert character.normalized_name == "林青岚"
            assert character.payload["aliases"] == ["青岚"]
            assert character.payload["normalized_aliases"] == ["青岚"]
            assert character.story_time_label == "三个月后"

            assert _count(session, Character) == 0
            assert _count(session, OrganizationEntity) == 0
            assert _count(session, Career) == 0
            assert _count(session, EntityProvenance) == 0
            assert _count(session, RelationshipTimelineEvent) == 0
            assert _count(session, WorldSettingResult) == 0


def test_unchanged_text_dedupe_reuses_completed_run_and_force_creates_new_run() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            chapter = _seed_project_with_golden_chapters(session)[2]
            fake = FakeExtractor(_fake_candidate_payload(chapter))

            first_run = extract_chapter_candidates(
                session,
                project_id="project-extraction",
                chapter_id=chapter.id,
                user_id="user-extraction",
                extractor=fake,
            )
            second_run = extract_chapter_candidates(
                session,
                project_id="project-extraction",
                chapter_id=chapter.id,
                user_id="user-extraction",
                extractor=fake,
            )
            session.flush()

            assert second_run.id == first_run.id
            assert fake.calls == 1
            assert _count(session, ExtractionRun) == 1
            assert _count(session, ExtractionCandidate) == 8

            forced_run = extract_chapter_candidates(
                session,
                project_id="project-extraction",
                chapter_id=chapter.id,
                user_id="user-extraction",
                extractor=fake,
                force=True,
            )
            session.flush()

            assert forced_run.id != first_run.id
            assert fake.calls == 2
            assert _count(session, ExtractionRun) == 2
            assert _count(session, ExtractionCandidate) == 16


def test_malformed_model_output_marks_failed_run_without_candidates_or_canonical_mutations(monkeypatch) -> None:
    network_attempts: list[tuple[object, object]] = []

    def fail_on_network(self, address):
        network_attempts.append((self, address))
        raise AssertionError(f"extraction test attempted network access: {address}")

    monkeypatch.setattr(socket.socket, "connect", fail_on_network)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            chapter = _seed_project_with_golden_chapters(session)[1]
            fake = FakeExtractor("这不是 JSON")

            run = extract_chapter_candidates(
                session,
                project_id="project-extraction",
                chapter_id=chapter.id,
                user_id="user-extraction",
                extractor=fake,
                trigger_source="manual",
                provider="fake-provider",
                model="fake-model",
            )
            session.flush()

            assert fake.calls == 1
            assert network_attempts == []
            assert _count(session, ExtractionRun) == 1
            assert run.status == "failed"
            assert "not valid JSON" in run.error_message
            assert run.provider == "fake-provider"
            assert run.model == "fake-model"
            assert chapter.content == load_golden_fixture()["chapters"][0]["content"]
            assert _count(session, ExtractionCandidate) == 0
            assert _count(session, Character) == 0
            assert _count(session, OrganizationEntity) == 0
            assert _count(session, Career) == 0
            assert _count(session, EntityProvenance) == 0
            assert _count(session, RelationshipTimelineEvent) == 0
            assert _count(session, WorldSettingResult) == 0
