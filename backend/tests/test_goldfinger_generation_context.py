import asyncio
import json
from collections.abc import Sequence
from typing import Protocol, TypeVar, cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Character,
    Chapter,
    ExtractionCandidate,
    ExtractionRun,
    Goldfinger,
    GoldfingerHistoryEvent,
    Outline,
    Project,
)
from app.services.chapter_context_service import OneToManyContextBuilder, OneToOneContextBuilder
from app.services.prompt_service import PromptService


PROJECT_ID = "project-goldfinger-generation-context"
USER_ID = "user-goldfinger-generation-context"
CHAPTER_ID = "chapter-goldfinger-generation-context"
OUTLINE_ID = "outline-goldfinger-generation-context"
OWNER_ID = "char-shen-goldfinger-generation-context"

RunSyncT = TypeVar("RunSyncT")
ScalarT = TypeVar("ScalarT", covariant=True)


class ScalarResultProtocol(Protocol[ScalarT]):
    def all(self) -> Sequence[ScalarT]: ...


class ExecuteResultProtocol(Protocol):
    def scalars(self) -> ScalarResultProtocol[object]: ...


class SyncSessionProtocol(Protocol):
    def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol: ...


class AsyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self.session: SyncSessionProtocol = cast(SyncSessionProtocol, session)

    async def execute(self, *args: object, **kwargs: object) -> ExecuteResultProtocol:
        return self.session.execute(*args, **kwargs)

    async def run_sync(self, fn):
        return fn(cast(Session, self.session))


def _session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:", future=True)
    connection = engine.connect()
    Base.metadata.create_all(connection)
    return Session(bind=connection)


def _seed_base(session: Session, *, outline_mention: str = "天命系统") -> None:
    expansion_plan = {
        "plot_summary": f"沈砚将验证{outline_mention}的任务规则。",
        "key_events": [f"{outline_mention}发布任务", "沈砚做出选择"],
        "character_focus": ["沈砚"],
        "emotional_tone": "紧张",
        "narrative_goal": "展示系统规则与限制",
        "conflict_type": "能力试炼",
    }
    outline_structure = {
        "summary": f"围绕{outline_mention}的触发条件推进剧情。",
        "characters": [{"name": "沈砚", "type": "character"}],
        "key_points": [f"{outline_mention}进入剧情焦点"],
        "goal": "明确金手指不会无条件开挂",
    }

    session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="金手指上下文", genre="玄幻", theme="成长"))
    session.add(Character(id=OWNER_ID, project_id=PROJECT_ID, name="沈砚", role_type="protagonist"))
    session.add(
        Outline(
            id=OUTLINE_ID,
            project_id=PROJECT_ID,
            title="系统试炼",
            content=f"本章必须处理{outline_mention}的规则。",
            structure=json.dumps(outline_structure, ensure_ascii=False),
            order_index=1,
        )
    )
    session.add(
        Chapter(
            id=CHAPTER_ID,
            project_id=PROJECT_ID,
            outline_id=OUTLINE_ID,
            chapter_number=1,
            title="系统苏醒",
            summary=f"{outline_mention}首次给出明确任务。",
            expansion_plan=json.dumps(expansion_plan, ensure_ascii=False),
            sub_index=1,
            status="draft",
        )
    )
    session.commit()


def _seed_pending_candidate(session: Session) -> None:
    session.add(
        ExtractionRun(
            id="run-pending-goldfinger-context",
            project_id=PROJECT_ID,
            chapter_id=CHAPTER_ID,
            trigger_source="manual",
            pipeline_version="test",
            schema_version="goldfinger-test",
            prompt_hash="prompt",
            content_hash="content",
            status="completed",
        )
    )
    session.add(
        ExtractionCandidate(
            id="candidate-pending-goldfinger-context",
            run_id="run-pending-goldfinger-context",
            project_id=PROJECT_ID,
            user_id=USER_ID,
            source_chapter_id=CHAPTER_ID,
            candidate_type="goldfinger",
            trigger_type="manual",
            source_hash="pending-source",
            display_name="伪系统候选",
            normalized_name="伪系统候选",
            status="pending",
            confidence=0.96,
            evidence_text="伪系统候选尚未通过评审",
            source_start_offset=0,
            source_end_offset=12,
            source_chapter_number=1,
            source_chapter_order=1,
            payload={"name": "伪系统候选", "status": "active"},
            raw_payload={"name": "伪系统候选", "status": "active"},
        )
    )
    session.commit()


def _build_one_to_many(session: Session):
    chapter = session.get(Chapter, CHAPTER_ID)
    project = session.get(Project, PROJECT_ID)
    outline = session.get(Outline, OUTLINE_ID)
    assert chapter is not None
    assert project is not None
    return asyncio.run(
        OneToManyContextBuilder().build(
            chapter=chapter,
            project=project,
            outline=outline,
            user_id=USER_ID,
            db=cast(object, AsyncSessionAdapter(session)),
        )
    )


def _build_one_to_one(session: Session):
    chapter = session.get(Chapter, CHAPTER_ID)
    project = session.get(Project, PROJECT_ID)
    outline = session.get(Outline, OUTLINE_ID)
    assert chapter is not None
    assert project is not None
    return asyncio.run(
        OneToOneContextBuilder().build(
            chapter=chapter,
            project=project,
            outline=outline,
            user_id=USER_ID,
            db=cast(object, AsyncSessionAdapter(session)),
        )
    )


def test_generation_context_includes_approved_goldfinger_and_excludes_pending_candidates() -> None:
    session = _session()
    _seed_base(session)
    session.add(
        Goldfinger(
            id="gf-approved-destiny-system",
            project_id=PROJECT_ID,
            name="天命系统",
            normalized_name="天命系统",
            owner_character_id=OWNER_ID,
            owner_character_name="沈砚",
            type="system",
            status="active",
            summary="发布任务并根据完成情况发放奖励",
            rules=["宿主主动接受任务后生效"],
            tasks=[{"title": "三日内救下师姐", "status": "active"}],
            rewards=[{"name": "悟性提升"}],
            limits=["冷却期间不能连续领取同类任务"],
            trigger_conditions=["濒死时首次激活"],
            cooldown={"chapters": 3},
            aliases=["系统", "天命面板"],
            source="extraction",
        )
    )
    session.add(
        GoldfingerHistoryEvent(
            id="history-approved-destiny-system",
            goldfinger_id="gf-approved-destiny-system",
            project_id=PROJECT_ID,
            chapter_id=CHAPTER_ID,
            event_type="created",
            evidence_excerpt="天命系统苏醒，发布三日救援任务并承诺悟性奖励",
            source_type="extraction",
        )
    )
    session.commit()
    _seed_pending_candidate(session)

    one_to_many_context = _build_one_to_many(session)
    assert one_to_many_context.goldfinger_context is not None
    assert "天命系统" in one_to_many_context.goldfinger_context
    assert "三日内救下师姐" in one_to_many_context.goldfinger_context
    assert "伪系统候选" not in one_to_many_context.goldfinger_context
    assert one_to_many_context.context_stats["goldfinger_count"] == 1
    assert one_to_many_context.context_stats["goldfinger_length"] == len(one_to_many_context.goldfinger_context)
    assert one_to_many_context.get_total_context_length() >= len(one_to_many_context.goldfinger_context)

    one_to_one_context = _build_one_to_one(session)
    assert one_to_one_context.goldfinger_context is not None
    assert "天命系统" in one_to_one_context.goldfinger_context
    assert "伪系统候选" not in one_to_one_context.goldfinger_context
    assert one_to_one_context.context_stats["goldfinger_count"] == 1

    prompt = PromptService.format_prompt(
        PromptService.CHAPTER_GENERATION_ONE_TO_MANY,
        project_title="金手指上下文",
        genre="玄幻",
        chapter_number=1,
        chapter_title="系统苏醒",
        chapter_outline=one_to_many_context.chapter_outline,
        target_word_count=3000,
        narrative_perspective="第三人称",
        characters_info=one_to_many_context.chapter_characters,
        goldfinger_context=one_to_many_context.goldfinger_context,
        chapter_careers="暂无职业信息",
        foreshadow_reminders="暂无需要关注的伏笔",
        relevant_memories="暂无相关记忆",
    )
    assert "<goldfingers" in prompt
    assert "天命系统" in prompt


def test_generation_context_enforces_goldfinger_count_history_and_summary_bounds() -> None:
    session = _session()
    _seed_base(session, outline_mention="系统11")
    statuses = ["active", "cooldown", "upgrading", "latent"]
    for index in range(12):
        goldfinger_id = f"gf-bound-{index:02d}"
        session.add(
            Goldfinger(
                id=goldfinger_id,
                project_id=PROJECT_ID,
                name=f"系统{index:02d}",
                normalized_name=f"系统{index:02d}",
                owner_character_id=OWNER_ID,
                owner_character_name="沈砚",
                type="system",
                status=statuses[index % len(statuses)],
                summary=f"系统{index:02d}概要" + "长" * 420,
                rules=[{"title": f"规则{index}", "description": "不可无限触发"}],
                tasks=[{"title": f"任务{index}"}],
                rewards=[{"name": f"奖励{index}"}],
                limits=[f"限制{index}"],
                trigger_conditions=[f"触发{index}"],
                cooldown={"chapters": index % 4 + 1},
                source="manual",
            )
        )
        for event_index in range(5):
            session.add(
                GoldfingerHistoryEvent(
                    id=f"history-bound-{index:02d}-{event_index}",
                    goldfinger_id=goldfinger_id,
                    project_id=PROJECT_ID,
                    chapter_id=CHAPTER_ID,
                    event_type=f"event-{event_index}",
                    evidence_excerpt=f"系统{index:02d}证据{event_index}",
                    source_type="manual",
                )
            )
    session.commit()

    context = _build_one_to_many(session)
    assert context.goldfinger_context is not None
    context_lines = context.goldfinger_context.splitlines()
    item_lines = [line for line in context_lines if line.startswith("- 【")]
    summary_lines = [line for line in context_lines if line.startswith("  概要：")]
    history_lines = [line for line in context_lines if line.startswith("  近期历史：")]

    assert context.context_stats["goldfinger_count"] == 8
    assert len(item_lines) == 8
    assert item_lines[0].startswith("- 【系统11】")
    assert all(len(line.removeprefix("  概要：")) <= 300 for line in summary_lines)
    assert len(history_lines) == 8
    for line in history_lines:
        events = line.removeprefix("  近期历史：").split("；")
        assert len(events) <= 3
