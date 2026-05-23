from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Project
from app.services.data_bank_service import DataBankService, DataBankValidationError, reject_remote_reference


pytestmark = pytest.mark.anyio


async def _seed_projects(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async with async_db_session() as session:
        session.add_all(
            [
                Project(id="project-rag-owner", user_id="user-rag-owner", title="资料库项目"),
                Project(id="project-rag-other", user_id="user-rag-owner", title="同用户其他项目"),
            ]
        )
        await session.commit()


async def test_deterministic_retrieval_trace(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    await _seed_projects(async_db_session)
    async with async_db_session() as session:
        first = await DataBankService.create_text_item(
            db=session,
            project_id="project-rag-owner",
            user_id="user-rag-owner",
            title="青岚阁档案",
            text="青岚阁只在暴雨夜打开山门。龙城来使必须等待三声钟响。",
            source_type="snippet",
        )
        second = await DataBankService.create_text_item(
            db=session,
            project_id="project-rag-owner",
            user_id="user-rag-owner",
            title="龙城档案",
            text="龙城建立在七层玄铁城墙之上，城门刻着旧王朝誓言。",
            source_type="snippet",
        )

        trace_one = await DataBankService.retrieve(
            db=session,
            project_id="project-rag-owner",
            user_id="user-rag-owner",
            query="青岚阁 龙城",
            limit=5,
        )
        trace_two = await DataBankService.retrieve(
            db=session,
            project_id="project-rag-owner",
            user_id="user-rag-owner",
            query="青岚阁 龙城",
            limit=5,
        )

    assert trace_one == trace_two
    assert trace_one.strategy == "deterministic-lexical-v1"
    assert trace_one.total_candidates == 2
    assert trace_one.returned_count == 2
    assert [result.item_id for result in trace_one.results] == [first.id, second.id]
    assert trace_one.results[0].order == 1
    assert trace_one.results[0].title == "青岚阁档案"
    assert "青岚阁" in trace_one.results[0].content
    assert trace_one.results[0].char_start == 0
    assert trace_one.results[0].char_end == len("青岚阁只在暴雨夜打开山门。龙城来使必须等待三声钟响。")
    assert trace_one.results[0].matched_terms


async def test_retrieval_is_project_scoped(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    await _seed_projects(async_db_session)
    async with async_db_session() as session:
        await DataBankService.create_text_item(
            db=session,
            project_id="project-rag-owner",
            user_id="user-rag-owner",
            title="本项目资料",
            text="星砂港的钥匙藏在主角袖中。",
        )
        await DataBankService.create_text_item(
            db=session,
            project_id="project-rag-other",
            user_id="user-rag-owner",
            title="其他项目资料",
            text="星砂港在另一个项目里有不同设定。",
        )

        owner_trace = await DataBankService.retrieve(
            db=session,
            project_id="project-rag-owner",
            user_id="user-rag-owner",
            query="星砂港",
            limit=10,
        )
        other_trace = await DataBankService.retrieve(
            db=session,
            project_id="project-rag-other",
            user_id="user-rag-owner",
            query="星砂港",
            limit=10,
        )

    assert owner_trace.returned_count == 1
    assert owner_trace.results[0].title == "本项目资料"
    assert other_trace.returned_count == 1
    assert other_trace.results[0].title == "其他项目资料"


def test_remote_url_rejected_by_service_boundary() -> None:
    with pytest.raises(DataBankValidationError):
        reject_remote_reference("https://example.com/novel.md")
