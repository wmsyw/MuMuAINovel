import json

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Chapter, Character, EntityProvenance, ExtractionCandidate, Goldfinger, GoldfingerHistoryEvent, Project
from app.services.chapter_fact_sync_service import ChapterFactSyncService
from app.services.goldfinger_sync_service import GoldfingerSyncService
from app.services.plot_analyzer import GOLDFINGER_CHANGE_FIELDS, PlotAnalyzer
from app.services.prompt_service import PromptService


PROJECT_ID = "project-goldfinger-sync"
USER_ID = "user-goldfinger-sync"
CHAPTER_ID = "chapter-goldfinger-sync"


class _ParserAIService:
    @staticmethod
    def _clean_json_response(response: str) -> str:
        return response


def _count(session: Session, model: type[object]) -> int:
    return int(session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one())


def _session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    connection = engine.connect()
    Base.metadata.create_all(connection)
    return Session(bind=connection)


def _seed_base(session: Session) -> None:
    session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="金手指同步"))
    session.add(
        Chapter(
            id=CHAPTER_ID,
            project_id=PROJECT_ID,
            chapter_number=1,
            title="系统苏醒",
            content="沈砚濒死时，天命系统苏醒，发布三日救援任务并承诺悟性奖励。",
            sub_index=1,
            status="published",
        )
    )
    session.add(Character(id="char-shen", project_id=PROJECT_ID, name="沈砚", role_type="protagonist"))
    session.commit()


def _goldfinger_run(session: Session):
    return ChapterFactSyncService(session).schedule_for_chapter(
        project_id=PROJECT_ID,
        chapter_id=CHAPTER_ID,
        content="沈砚濒死时，天命系统苏醒，发布三日救援任务并承诺悟性奖励。",
        source="manual_sync",
        entity_types=["goldfinger"],
    )[0]


def test_plot_analysis_prompt_and_parser_preserve_goldfinger_changes_schema() -> None:
    assert "goldfinger_changes" in PromptService.PLOT_ANALYSIS
    for field in GOLDFINGER_CHANGE_FIELDS:
        assert field in PromptService.PLOT_ANALYSIS

    parser = PlotAnalyzer(_ParserAIService())
    parsed = parser._parse_analysis_response(json.dumps({"hooks": [], "plot_points": [], "scores": {}, "goldfinger_changes": [{"name": "天命系统", "confidence": "0.97"}]}, ensure_ascii=False))

    assert parsed is not None
    change = parsed["goldfinger_changes"][0]
    assert set(GOLDFINGER_CHANGE_FIELDS).issubset(change)
    assert change["name"] == "天命系统"
    assert change["normalized_name"] == "天命系统"
    assert change["operation"] == "upsert"
    assert change["confidence"] == 0.97


def test_goldfinger_high_confidence_extraction_auto_merges_with_history_and_provenance() -> None:
    session = _session()
    _seed_base(session)
    run = _goldfinger_run(session)

    results = GoldfingerSyncService(session).process_run_changes(
        run.id,
        [
            {
                "name": "天命系统",
                "owner_character_name": "沈砚",
                "type": "system",
                "status": "active",
                "summary": "发布任务并根据完成情况发放奖励",
                "rules": ["宿主主动接受任务后生效"],
                "tasks": [{"title": "三日内救下师姐", "status": "active"}],
                "rewards": [{"name": "悟性提升"}],
                "limits": ["冷却期间不能连续领取同类任务"],
                "trigger_conditions": ["濒死时首次激活"],
                "cooldown": {"chapters": 3},
                "aliases": ["系统", "天命面板"],
                "operation": "upsert",
                "evidence_excerpt": "天命系统苏醒，发布三日救援任务并承诺悟性奖励",
                "confidence": 0.96,
            }
        ],
    )
    session.commit()

    assert len(results) == 1
    assert results[0].changed is True
    assert _count(session, Goldfinger) == 1
    assert _count(session, ExtractionCandidate) == 1
    assert _count(session, GoldfingerHistoryEvent) == 1
    assert _count(session, EntityProvenance) == 1
    goldfinger = session.execute(sa.select(Goldfinger)).scalar_one()
    assert goldfinger.name == "天命系统"
    assert goldfinger.owner_character_id == "char-shen"
    assert goldfinger.status == "active"
    assert goldfinger.aliases == ["系统", "天命面板"]
    assert goldfinger.goldfinger_metadata is None
    candidate = session.execute(sa.select(ExtractionCandidate)).scalar_one()
    assert candidate.status == "accepted"
    assert candidate.canonical_target_type == "goldfinger"
    assert candidate.payload["merge_decision"]["action"] == "accepted"
    history = session.execute(sa.select(GoldfingerHistoryEvent)).scalar_one()
    assert history.source_type == "extraction"
    assert history.evidence_excerpt == "天命系统苏醒，发布三日救援任务并承诺悟性奖励"


def test_goldfinger_risky_extractions_remain_pending_without_canonical_overwrite() -> None:
    session = _session()
    _seed_base(session)
    session.add_all([
        Character(id="char-qing-a", project_id=PROJECT_ID, name="青岚"),
        Character(id="char-qing-b", project_id=PROJECT_ID, name="青岚"),
        Goldfinger(
            id="gf-existing",
            project_id=PROJECT_ID,
            name="天命系统",
            normalized_name="天命系统",
            owner_character_id="char-shen",
            owner_character_name="沈砚",
            type="system",
            status="active",
            rules=["宿主主动接受任务后生效"],
            source="manual",
        ),
    ])
    session.commit()
    run = _goldfinger_run(session)

    results = GoldfingerSyncService(session).process_run_changes(
        run.id,
        [
            {"name": "洞察之眼", "type": "ability", "status": "active", "evidence_excerpt": "洞察之眼短暂亮起", "confidence": 0.5},
            {"name": "青岚血脉", "owner_character_name": "青岚", "type": "bloodline", "status": "latent", "evidence_excerpt": "青岚血脉浮现", "confidence": 0.95},
            {"name": "天命系统", "owner_character_name": "沈砚", "type": "system", "status": "sealed", "rules": ["系统强制抹杀失败者"], "evidence_excerpt": "天命系统仍保持开启", "confidence": 0.96},
        ],
    )
    session.commit()

    reasons = {result.reason for result in results}
    assert {"low_confidence", "owner_ambiguity", "status_contradiction"}.issubset(reasons)
    assert _count(session, Goldfinger) == 1
    assert _count(session, GoldfingerHistoryEvent) == 0
    assert _count(session, EntityProvenance) == 0
    existing = session.get(Goldfinger, "gf-existing")
    assert existing is not None
    assert existing.status == "active"
    assert existing.rules == ["宿主主动接受任务后生效"]
    pending = session.execute(sa.select(ExtractionCandidate).where(ExtractionCandidate.status == "pending")).scalars().all()
    assert len(pending) == 3
    assert {candidate.review_required_reason for candidate in pending} == {"low_confidence", "owner_ambiguity", "status_contradiction"}


def test_goldfinger_reprocessing_same_run_is_idempotent_for_candidates_rows_and_history() -> None:
    session = _session()
    _seed_base(session)
    run = _goldfinger_run(session)
    change = {
        "name": "天命系统",
        "owner_character_name": "沈砚",
        "type": "system",
        "status": "active",
        "summary": "发布任务并发放奖励",
        "tasks": [{"title": "三日内救下师姐"}],
        "rewards": [{"name": "悟性提升"}],
        "aliases": ["系统"],
        "evidence_excerpt": "天命系统苏醒，发布三日救援任务并承诺悟性奖励",
        "confidence": 0.96,
    }

    service = GoldfingerSyncService(session)
    first = service.process_run_changes(run.id, [change])
    second = service.process_run_changes(run.id, [change])
    session.commit()

    assert first[0].changed is True
    assert second[0].changed is False
    assert second[0].reason == "candidate is accepted"
    assert _count(session, Goldfinger) == 1
    assert _count(session, ExtractionCandidate) == 1
    assert _count(session, GoldfingerHistoryEvent) == 1
    assert _count(session, EntityProvenance) == 1
