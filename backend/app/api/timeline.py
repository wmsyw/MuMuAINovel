"""Timeline projection query API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import verify_project_access
from app.database import get_db
from app.models.chapter import Chapter
from app.models.relationship import RelationshipTimelineEvent
from app.schemas.timeline import (
    TimelineEventResponse,
    TimelineEventType,
    TimelineHistoryResponse,
    TimelineQueryPoint,
    TimelineStateResponse,
)
from app.services.timeline_projection_service import TimelineProjectionService

router = APIRouter(prefix="/timeline", tags=["时间线查询"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


async def _resolve_timeline_point(
    *,
    project_id: str,
    chapter_id: str | None,
    chapter_number: int | None,
    chapter_order: int | None,
    db: AsyncSession,
) -> TimelineQueryPoint:
    if chapter_id is not None:
        result = await db.execute(select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id))
        chapter = result.scalar_one_or_none()
        if chapter is None:
            raise HTTPException(status_code=404, detail="章节不存在或不属于项目")
        resolved_number = int(chapter.chapter_number)
        return TimelineQueryPoint(
            chapter_id=chapter.id,
            chapter_number=resolved_number,
            chapter_order=chapter_order if chapter_order is not None else resolved_number,
        )

    if chapter_number is None:
        result = await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.chapter_number.desc(), Chapter.id.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest is None:
            raise HTTPException(status_code=422, detail="缺少 chapter_id 或 chapter_number")
        resolved_number = int(latest.chapter_number)
        return TimelineQueryPoint(
            chapter_id=latest.id,
            chapter_number=resolved_number,
            chapter_order=chapter_order if chapter_order is not None else resolved_number,
        )

    return TimelineQueryPoint(
        chapter_id=None,
        chapter_number=chapter_number,
        chapter_order=chapter_order if chapter_order is not None else chapter_number,
    )


@router.get("/projects/{project_id}/state", response_model=TimelineStateResponse, summary="查询项目时间线当前状态")
async def get_timeline_state(
    project_id: str,
    request: Request,
    chapter_id: str | None = Query(None, description="章节ID；优先于 chapter_number"),
    chapter_number: int | None = Query(None, ge=0, description="章节序号；省略时使用项目最新章节"),
    chapter_order: int | None = Query(None, ge=0, description="章节内/故事顺序；省略时使用章节序号"),
    db: AsyncSession = Depends(get_db),
) -> TimelineStateResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(project_id, user_id, db)
    point = await _resolve_timeline_point(
        project_id=project_id,
        chapter_id=chapter_id,
        chapter_number=chapter_number,
        chapter_order=chapter_order,
        db=db,
    )

    state = await db.run_sync(
        lambda session: TimelineProjectionService(session).project_state(
            project_id=project_id,
            chapter_number=point.chapter_number,
            chapter_order=point.chapter_order,
        )
    )
    return TimelineStateResponse(
        project_id=project_id,
        point=point,
        relationships=[TimelineEventResponse.model_validate(event) for event in state["relationships"]],
        affiliations=[TimelineEventResponse.model_validate(event) for event in state["affiliations"]],
        professions=[TimelineEventResponse.model_validate(event) for event in state["professions"]],
    )


@router.get("/projects/{project_id}/history", response_model=TimelineHistoryResponse, summary="查询项目时间线历史")
async def list_timeline_history(
    project_id: str,
    request: Request,
    event_type: TimelineEventType | None = Query(None, description="事件类型过滤"),
    db: AsyncSession = Depends(get_db),
) -> TimelineHistoryResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(project_id, user_id, db)
    events: list[RelationshipTimelineEvent] = await db.run_sync(
        lambda session: TimelineProjectionService(session).history(project_id=project_id, event_type=event_type)
    )
    return TimelineHistoryResponse(
        project_id=project_id,
        event_type=event_type,
        total=len(events),
        items=[TimelineEventResponse.model_validate(event) for event in events],
    )
