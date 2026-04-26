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
)
from app.services.candidate_merge_service import CandidateMergeService
from app.services.timeline_projection_service import TimelineProjectionService


def _count(session: Session, model: type[object]) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def _seed_timeline_project(session: Session) -> dict[int, Chapter]:
    project = Project(id="project-timeline", user_id="user-timeline", title="关系年表")
    session.add(project)
    chapters: dict[int, Chapter] = {}
    for number in (1, 5, 9):
        chapter = Chapter(
            id=f"chapter-{number}",
            project_id=project.id,
            chapter_number=number,
            title=f"第{number}章",
            content="林青岚、沈砚、巡星司、星图会、剑修、星术师。",
            sub_index=number,
            status="published",
        )
        session.add(chapter)
        chapters[number] = chapter
    session.add(
        ExtractionRun(
            id="run-timeline",
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
    session.add_all([
        Character(id="char-linqinglan", project_id=project.id, name="林青岚"),
        Character(id="char-shenyan", project_id=project.id, name="沈砚"),
        OrganizationEntity(id="org-xunxing", project_id=project.id, name="巡星司", normalized_name="巡星司"),
        OrganizationEntity(id="org-xingtu", project_id=project.id, name="星图会", normalized_name="星图会"),
        Career(id="career-sword", project_id=project.id, name="剑修", type="main", stages="[]", max_stage=9),
        Career(id="career-star", project_id=project.id, name="星术师", type="main", stages="[]", max_stage=6),
    ])
    session.flush()
    return chapters


def _candidate(
    session: Session,
    *,
    candidate_id: str,
    candidate_type: str,
    display_name: str,
    payload: dict[str, object],
    chapter: Chapter,
    confidence: float = 0.95,
) -> ExtractionCandidate:
    candidate = ExtractionCandidate(
        id=candidate_id,
        run_id="run-timeline",
        project_id="project-timeline",
        user_id="user-timeline",
        source_chapter_id=chapter.id,
        source_chapter_start_id=chapter.id,
        source_chapter_end_id=chapter.id,
        candidate_type=candidate_type,
        trigger_type="manual",
        source_hash=f"source-{candidate_id}",
        display_name=display_name,
        normalized_name=display_name,
        canonical_target_type={"organization_affiliation": "organization", "profession_assignment": "career"}.get(candidate_type),
        status="pending",
        confidence=confidence,
        evidence_text=display_name,
        source_start_offset=0,
        source_end_offset=len(display_name),
        source_chapter_number=chapter.chapter_number,
        source_chapter_order=chapter.chapter_number,
        valid_from_chapter_id=chapter.id,
        valid_from_chapter_order=chapter.chapter_number,
        story_time_label=f"第{chapter.chapter_number}章",
        payload={"display_name": display_name, "normalized_name": display_name, **payload},
        raw_payload={"candidate_type": candidate_type, **payload},
    )
    session.add(candidate)
    session.flush()
    return candidate


def test_relationship_timeline_projects_chapter_three_six_and_ten_state_with_history() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            chapters = _seed_timeline_project(session)
            service = CandidateMergeService(session)
            start = _candidate(
                session,
                candidate_id="rel-start",
                candidate_type="relationship",
                display_name="盟友",
                payload={"participants": ["林青岚", "沈砚"], "relationship": "盟友"},
                chapter=chapters[1],
            )
            contradiction = _candidate(
                session,
                candidate_id="rel-contradiction",
                candidate_type="relationship",
                display_name="仇敌",
                payload={"participants": ["林青岚", "沈砚"], "relationship": "仇敌"},
                chapter=chapters[5],
            )
            changed = _candidate(
                session,
                candidate_id="rel-changed",
                candidate_type="relationship",
                display_name="敌对盟友",
                payload={"participants": ["林青岚", "沈砚"], "relationship": "敌对盟友"},
                chapter=chapters[5],
            )
            ended = _candidate(
                session,
                candidate_id="rel-ended",
                candidate_type="relationship",
                display_name="关系结束",
                payload={"participants": ["林青岚", "沈砚"], "relationship": "敌对盟友", "status": "ended"},
                chapter=chapters[9],
            )

            assert service.accept_candidate(start.id).changed is True
            assert service.accept_candidate(contradiction.id).changed is False
            assert contradiction.status == "pending"
            assert _count(session, RelationshipTimelineEvent) == 1
            assert service.accept_candidate(changed.id, override=True).changed is True
            assert service.accept_candidate(ended.id, override=True).changed is True

            projection = TimelineProjectionService(session)
            chapter_3 = projection.active_relationships(project_id="project-timeline", chapter_number=3)
            chapter_6 = projection.active_relationships(project_id="project-timeline", chapter_number=6)
            chapter_10 = projection.active_relationships(project_id="project-timeline", chapter_number=10)
            history = projection.history(project_id="project-timeline", event_type="relationship")

            assert [event.relationship_name for event in chapter_3] == ["盟友"]
            assert [event.relationship_name for event in chapter_6] == ["敌对盟友"]
            assert chapter_10 == []
            assert [event.relationship_name for event in history] == ["盟友", "敌对盟友", "敌对盟友"]
            assert history[-1].event_status == "ended"
            assert _count(session, EntityProvenance) == 3


def test_affiliation_and_profession_assignment_projection_at_chapter_three_six_and_ten() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            chapters = _seed_timeline_project(session)
            service = CandidateMergeService(session)
            aff_start = _candidate(
                session,
                candidate_id="aff-start",
                candidate_type="organization_affiliation",
                display_name="巡星司外勤",
                payload={"character": "林青岚", "current_organization": "巡星司", "position": "外勤"},
                chapter=chapters[1],
            )
            aff_change = _candidate(
                session,
                candidate_id="aff-change",
                candidate_type="organization_affiliation",
                display_name="星图会顾问",
                payload={"character": "林青岚", "current_organization": "星图会", "position": "顾问"},
                chapter=chapters[5],
            )
            prof_start = _candidate(
                session,
                candidate_id="prof-start",
                candidate_type="profession_assignment",
                display_name="剑修二阶",
                payload={"character": "林青岚", "profession": "剑修", "stage": 2},
                chapter=chapters[1],
            )
            prof_change = _candidate(
                session,
                candidate_id="prof-change",
                candidate_type="profession_assignment",
                display_name="星术师四阶",
                payload={"character": "林青岚", "profession": "星术师", "stage": 4},
                chapter=chapters[5],
            )

            assert service.accept_candidate(aff_start.id).changed is True
            assert service.accept_candidate(prof_start.id).changed is True
            assert service.accept_candidate(aff_change.id, override=True).changed is True
            assert service.accept_candidate(prof_change.id, override=True).changed is True

            projection = TimelineProjectionService(session)
            state_3 = projection.project_state(project_id="project-timeline", chapter_number=3)
            state_6 = projection.project_state(project_id="project-timeline", chapter_number=6)
            state_10 = projection.project_state(project_id="project-timeline", chapter_number=10)

            assert [(event.organization_entity_id, event.position) for event in state_3["affiliations"]] == [("org-xunxing", "外勤")]
            assert [(event.career_id, event.career_stage) for event in state_3["professions"]] == [("career-sword", 2)]
            assert [(event.organization_entity_id, event.position) for event in state_6["affiliations"]] == [("org-xingtu", "顾问")]
            assert [(event.career_id, event.career_stage) for event in state_6["professions"]] == [("career-star", 4)]
            assert [(event.organization_entity_id, event.position) for event in state_10["affiliations"]] == [("org-xingtu", "顾问")]
            assert [(event.career_id, event.career_stage) for event in state_10["professions"]] == [("career-star", 4)]
            assert len(projection.history(project_id="project-timeline", event_type="affiliation")) == 2
            assert len(projection.history(project_id="project-timeline", event_type="profession")) == 2
