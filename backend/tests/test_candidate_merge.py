import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Career,
    Chapter,
    Character,
    EntityAlias,
    EntityProvenance,
    ExtractionCandidate,
    ExtractionRun,
    OrganizationEntity,
    Project,
    RelationshipTimelineEvent,
)
from app.services.candidate_merge_service import CandidateMergeService


def _count(session: Session, model: type[object]) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def _seed_project(session: Session) -> dict[int, Chapter]:
    project = Project(id="project-merge", user_id="user-merge", title="星图旧案")
    session.add(project)
    chapters = {}
    for number in (1, 5):
        chapter = Chapter(
            id=f"chapter-{number}",
            project_id=project.id,
            chapter_number=number,
            title=f"第{number}章",
            content="林青岚在巡星司见到沈砚，后来转为星图会顾问。",
            sub_index=number,
            status="published",
        )
        session.add(chapter)
        chapters[number] = chapter
    session.add(
        ExtractionRun(
            id="run-merge",
            project_id=project.id,
            chapter_id="chapter-1",
            trigger_source="manual",
            pipeline_version="test",
            schema_version="test",
            prompt_hash="prompt",
            content_hash="content",
            status="completed",
        )
    )
    session.flush()
    return chapters


def _candidate(
    session: Session,
    *,
    candidate_id: str,
    candidate_type: str,
    display_name: str,
    payload: dict[str, object] | None = None,
    confidence: float = 0.95,
    chapter_id: str = "chapter-1",
    chapter_number: int = 1,
) -> ExtractionCandidate:
    candidate = ExtractionCandidate(
        id=candidate_id,
        run_id="run-merge",
        project_id="project-merge",
        user_id="user-merge",
        source_chapter_id=chapter_id,
        source_chapter_start_id=chapter_id,
        source_chapter_end_id=chapter_id,
        candidate_type=candidate_type,
        trigger_type="manual",
        source_hash=f"source-{candidate_id}",
        display_name=display_name,
        normalized_name=display_name,
        canonical_target_type={"character": "character", "organization": "organization", "profession": "career"}.get(candidate_type),
        status="pending",
        confidence=confidence,
        evidence_text=display_name,
        source_start_offset=0,
        source_end_offset=len(display_name),
        source_chapter_number=chapter_number,
        source_chapter_order=chapter_number,
        valid_from_chapter_id=chapter_id,
        valid_from_chapter_order=chapter_number,
        story_time_label=f"第{chapter_number}章",
        payload={
            "display_name": display_name,
            "normalized_name": display_name,
            "aliases": [],
            **(payload or {}),
        },
        raw_payload={"candidate_type": candidate_type, "display_name": display_name},
    )
    session.add(candidate)
    session.flush()
    return candidate


def test_accept_merge_entity_candidates_are_idempotent_and_preserve_provenance_aliases() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_project(session)
            existing_org = OrganizationEntity(
                id="org-existing",
                project_id="project-merge",
                name="巡星司",
                normalized_name="巡星司",
                source="manual",
            )
            session.add(existing_org)
            char_candidate = _candidate(
                session,
                candidate_id="cand-char",
                candidate_type="character",
                display_name="沈砚",
                payload={"aliases": ["沈先生"], "gender": "男"},
            )
            org_candidate = _candidate(
                session,
                candidate_id="cand-org",
                candidate_type="organization",
                display_name="巡星司",
                payload={"aliases": ["星司"]},
            )
            career_candidate = _candidate(
                session,
                candidate_id="cand-career",
                candidate_type="profession",
                display_name="星术师",
                payload={"aliases": ["观星术士"], "max_stage": 6},
            )

            service = CandidateMergeService(session)
            assert service.accept_candidate(char_candidate.id, reviewer_user_id="reviewer").changed is True
            assert service.merge_candidate(org_candidate.id, target_type="organization", target_id=existing_org.id).changed is True
            assert service.accept_candidate(career_candidate.id).changed is True
            first_counts = {
                "characters": _count(session, Character),
                "organizations": _count(session, OrganizationEntity),
                "careers": _count(session, Career),
                "provenance": _count(session, EntityProvenance),
                "aliases": _count(session, EntityAlias),
            }

            service.accept_candidate(char_candidate.id, reviewer_user_id="reviewer")
            service.merge_candidate(org_candidate.id, target_type="organization", target_id=existing_org.id)
            service.accept_candidate(career_candidate.id)
            second_counts = {
                "characters": _count(session, Character),
                "organizations": _count(session, OrganizationEntity),
                "careers": _count(session, Career),
                "provenance": _count(session, EntityProvenance),
                "aliases": _count(session, EntityAlias),
            }

            assert first_counts == second_counts == {
                "characters": 1,
                "organizations": 1,
                "careers": 1,
                "provenance": 3,
                "aliases": 6,
            }
            assert char_candidate.status == "accepted"
            assert org_candidate.status == "merged"
            assert career_candidate.status == "accepted"
            assert all(candidate.reviewed_at is not None for candidate in (char_candidate, org_candidate, career_candidate))
            assert all(candidate.accepted_at is not None for candidate in (char_candidate, org_candidate, career_candidate))
            aliases = session.execute(sa.select(EntityAlias.entity_type, EntityAlias.alias)).all()
            assert ("character", "沈先生") in aliases
            assert ("organization", "星司") in aliases
            assert ("career", "观星术士") in aliases


def test_ambiguous_duplicate_and_cross_type_safe_auto_merge_remain_pending_without_mutation() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_project(session)
            session.add_all([
                Character(id="char-a", project_id="project-merge", name="青岚"),
                Character(id="char-b", project_id="project-merge", name="青岚"),
                OrganizationEntity(id="org-x", project_id="project-merge", name="巡星司", normalized_name="巡星司"),
            ])
            ambiguous = _candidate(
                session,
                candidate_id="cand-ambiguous",
                candidate_type="character",
                display_name="青岚",
            )
            cross_type = _candidate(
                session,
                candidate_id="cand-cross-type",
                candidate_type="character",
                display_name="巡星司",
            )
            before = (_count(session, Character), _count(session, OrganizationEntity), _count(session, EntityProvenance), _count(session, EntityAlias))

            results = CandidateMergeService(session).safe_auto_merge_pending(project_id="project-merge")
            after = (_count(session, Character), _count(session, OrganizationEntity), _count(session, EntityProvenance), _count(session, EntityAlias))

            assert before == after
            assert {result.changed for result in results} == {False}
            assert ambiguous.status == "pending"
            assert cross_type.status == "pending"
            assert ambiguous.canonical_target_id is None
            assert cross_type.canonical_target_id is None


def test_rollback_supersedes_accepted_rows_without_hard_deleting_history() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            _seed_project(session)
            character = Character(id="char-linqinglan", project_id="project-merge", name="林青岚")
            organization = OrganizationEntity(id="org-xunxing", project_id="project-merge", name="巡星司", normalized_name="巡星司")
            session.add_all([character, organization])
            affiliation = _candidate(
                session,
                candidate_id="cand-affiliation",
                candidate_type="organization_affiliation",
                display_name="巡星司",
                payload={"character": "林青岚", "current_organization": "巡星司", "position": "外勤"},
            )

            service = CandidateMergeService(session)
            assert service.accept_candidate(affiliation.id).changed is True
            assert affiliation.status == "merged"
            assert _count(session, EntityProvenance) == 1
            assert _count(session, RelationshipTimelineEvent) == 1

            assert service.rollback_candidate(affiliation.id, reviewer_user_id="reviewer", reason="bad extraction").changed is True
            assert service.rollback_candidate(affiliation.id, reviewer_user_id="reviewer").changed is False

            assert affiliation.status == "superseded"
            assert _count(session, EntityProvenance) == 1
            assert _count(session, RelationshipTimelineEvent) == 1
            provenance = session.execute(sa.select(EntityProvenance)).scalar_one()
            event = session.execute(sa.select(RelationshipTimelineEvent)).scalar_one()
            assert provenance.status == "rolled_back"
            assert event.event_status == "rolled_back"
            assert event.evidence_text == "巡星司"
