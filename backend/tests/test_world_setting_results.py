from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Project, WorldSettingResult
from app.services.legacy_backfill_service import LEGACY_SOURCE_TYPE
from app.services.world_setting_result_service import WorldSettingResultService


def _count(session: Session, model: type[object]) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


def _seed_project(session: Session) -> Project:
    project = Project(
        id="project-world",
        user_id="user-world",
        title="星潮纪事",
        description="世界观版本测试",
        world_time_period="旧纪元三百年",
        world_location="旧都群岛",
        world_atmosphere="潮湿阴郁",
        world_rules="月潮决定灵能强弱",
    )
    session.add(project)
    session.flush()
    return project


def _seed_legacy_accepted_result(session: Session, project: Project) -> WorldSettingResult:
    result = WorldSettingResult(
        id="world-legacy",
        project_id=project.id,
        run_id=None,
        status="accepted",
        world_time_period=project.world_time_period,
        world_location=project.world_location,
        world_atmosphere=project.world_atmosphere,
        world_rules=project.world_rules,
        prompt=None,
        provider=None,
        model=None,
        reasoning_intensity=None,
        raw_result={
            "world_time_period": project.world_time_period,
            "world_location": project.world_location,
            "world_atmosphere": project.world_atmosphere,
            "world_rules": project.world_rules,
        },
        source_type=LEGACY_SOURCE_TYPE,
        accepted_at=datetime(2026, 4, 26, 8, 0, 0),
        accepted_by=project.user_id,
    )
    session.add(result)
    session.flush()
    return result


def test_generation_creates_pending_result_without_overwrite() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            project = _seed_project(session)
            original_snapshot = (
                project.world_time_period,
                project.world_location,
                project.world_atmosphere,
                project.world_rules,
            )

            result = WorldSettingResultService(session).create_pending_result(
                project_id=project.id,
                world_time_period="星历一千年",
                world_location="浮空城与潮汐海",
                world_atmosphere="明亮但危机四伏",
                world_rules="星潮每十日改变一次法则",
                run_id="run-world-1",
                provider="openai",
                model="gpt-5-mini",
                reasoning_intensity="medium",
                prompt="生成世界观",
                prompt_version="world-v2",
                template_version="template-2026-04",
                raw_payload={"provider_response_id": "resp_123", "tokens": 321},
                actor_user_id="user-world",
            )

            session.refresh(project)
            assert result.status == "pending"
            assert result.accepted_at is None
            assert result.accepted_by is None
            assert result.source_type == "ai"
            assert result.provider == "openai"
            assert result.model == "gpt-5-mini"
            assert result.reasoning_intensity == "medium"
            assert result.raw_result["provider_response_id"] == "resp_123"
            assert result.raw_result["prompt_version"] == "world-v2"
            assert result.raw_result["template_version"] == "template-2026-04"
            assert result.raw_result["created_by"] == "user-world"
            assert (
                project.world_time_period,
                project.world_location,
                project.world_atmosphere,
                project.world_rules,
            ) == original_snapshot


def test_accept_result_updates_active_snapshot_and_audit() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            project = _seed_project(session)
            legacy = _seed_legacy_accepted_result(session, project)
            service = WorldSettingResultService(session)
            result = service.create_pending_result(
                project_id=project.id,
                world_time_period="新纪元元年",
                world_location="群星裂谷",
                world_atmosphere="壮阔紧张",
                world_rules="星核契约会反噬说谎者",
                provider="openai",
                model="gpt-5-mini",
                reasoning_intensity="high",
                raw_payload={"candidate": "world-v2"},
            )

            first = service.accept_result(result.id, accepted_by="reviewer-world")
            counts_after_first = _count(session, WorldSettingResult)
            active_snapshot = (
                project.world_time_period,
                project.world_location,
                project.world_atmosphere,
                project.world_rules,
            )
            second = service.accept_result(result.id, accepted_by="reviewer-world")
            counts_after_second = _count(session, WorldSettingResult)

            assert first.changed is True
            assert second.changed is False
            assert counts_after_first == counts_after_second == 2
            assert active_snapshot == (
                "新纪元元年",
                "群星裂谷",
                "壮阔紧张",
                "星核契约会反噬说谎者",
            )
            assert (
                project.world_time_period,
                project.world_location,
                project.world_atmosphere,
                project.world_rules,
            ) == active_snapshot
            assert result.status == "accepted"
            assert result.accepted_at is not None
            assert result.accepted_by == "reviewer-world"
            assert result.supersedes_result_id == legacy.id
            assert legacy.status == "superseded"
            assert legacy.source_type == LEGACY_SOURCE_TYPE


def test_rollback_restores_previous_accepted_snapshot() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            project = _seed_project(session)
            legacy = _seed_legacy_accepted_result(session, project)
            service = WorldSettingResultService(session)
            current = service.create_pending_result(
                project_id=project.id,
                world_time_period="灾后第七年",
                world_location="坠星荒原",
                world_atmosphere="冷硬肃杀",
                world_rules="古神遗骨污染所有法术",
                raw_payload={"candidate": "world-v3"},
            )
            _ = service.accept_result(current.id, accepted_by="reviewer-world")
            current.accepted_at = legacy.accepted_at + timedelta(hours=1)
            session.flush()
            assert project.world_time_period == "灾后第七年"
            assert legacy.status == "superseded"

            rollback = service.rollback_result(current.id, actor_user_id="reviewer-world")
            counts_after_rollback = _count(session, WorldSettingResult)
            repeat = service.rollback_result(current.id, actor_user_id="reviewer-world")

            assert rollback.changed is True
            assert rollback.previous_result == legacy
            assert repeat.changed is False
            assert counts_after_rollback == _count(session, WorldSettingResult) == 2
            assert current.status == "superseded"
            assert current.supersedes_result_id == legacy.id
            assert legacy.status == "accepted"
            assert project.world_time_period == "旧纪元三百年"
            assert project.world_location == "旧都群岛"
            assert project.world_atmosphere == "潮湿阴郁"
            assert project.world_rules == "月潮决定灵能强弱"

            history = session.execute(
                sa.select(WorldSettingResult).where(WorldSettingResult.project_id == project.id).order_by(WorldSettingResult.id)
            ).scalars().all()
            assert {row.id for row in history} == {"world-legacy", current.id}
            assert {row.status for row in history} == {"accepted", "superseded"}


def test_rollback_prefers_supersedes_link_when_legacy_accepted_at_is_null() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        with Session(bind=connection) as session:
            project = _seed_project(session)
            legacy = _seed_legacy_accepted_result(session, project)
            legacy.accepted_at = None
            service = WorldSettingResultService(session)
            current = service.create_pending_result(
                project_id=project.id,
                world_time_period="星潮复苏三十年",
                world_location="雾港、星塔、黑潮海",
                world_atmosphere="宏大、神秘、压迫",
                world_rules="潮汐魔力每七日涨落；星塔保存古代契约；守夜人拥有夜禁执法权。",
                raw_payload={"candidate": "world-v4"},
            )
            accepted = service.accept_result(current.id, accepted_by="reviewer-world")
            assert accepted.previous_result == legacy
            assert current.supersedes_result_id == legacy.id
            assert legacy.status == "superseded"
            assert legacy.accepted_at is None
            assert project.world_time_period == "星潮复苏三十年"

            rollback = service.rollback_result(current.id, actor_user_id="reviewer-world")
            repeat = service.rollback_result(current.id, actor_user_id="reviewer-world")

            assert rollback.changed is True
            assert rollback.previous_result == legacy
            assert repeat.changed is False
            assert repeat.reason == "already rolled back"
            assert current.status == "superseded"
            assert legacy.status == "accepted"
            assert legacy.accepted_at is not None
            assert project.world_time_period == "旧纪元三百年"
            assert project.world_location == "旧都群岛"
            assert project.world_atmosphere == "潮湿阴郁"
            assert project.world_rules == "月潮决定灵能强弱"


def test_world_setting_result_schema_basics_remain_registered() -> None:
    world_columns = {column.name for column in Base.metadata.tables["world_setting_results"].columns}
    project_columns = {column.name for column in Base.metadata.tables["projects"].columns}

    assert {
        "project_id",
        "run_id",
        "status",
        "world_time_period",
        "world_location",
        "world_atmosphere",
        "world_rules",
        "prompt",
        "provider",
        "model",
        "reasoning_intensity",
        "raw_result",
        "source_type",
        "accepted_at",
        "accepted_by",
        "supersedes_result_id",
    }.issubset(world_columns)
    assert {
        "world_time_period",
        "world_location",
        "world_atmosphere",
        "world_rules",
    }.issubset(project_columns)
