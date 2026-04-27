"""World-setting result review API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.common import verify_project_access
from app.database import get_db
from app.models.project import Project
from app.models.relationship import WorldSettingResult
from app.schemas.world_setting_result import (
    ProjectWorldSnapshot,
    WorldSettingRejectRequest,
    WorldSettingResultListResponse,
    WorldSettingResultOperationResponse,
    WorldSettingResultResponse,
    WorldSettingResultStatus,
    WorldSettingRollbackRequest,
)
from app.services.world_setting_result_service import WorldSettingOperationResult, WorldSettingResultService

router = APIRouter(prefix="/world-setting-results", tags=["世界观结果"])


@dataclass(slots=True)
class _SerializedOperationResult:
    changed: bool
    reason: str | None
    result: WorldSettingResultResponse | None
    previous_result: WorldSettingResultResponse | None
    active_world: ProjectWorldSnapshot | None


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _structured_error(status_code: int, *, code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _get_result_for_user(result_id: str, user_id: str, db: AsyncSession) -> WorldSettingResult:
    result = await db.execute(select(WorldSettingResult).where(WorldSettingResult.id == result_id))
    world_result = result.scalar_one_or_none()
    if world_result is None:
        raise HTTPException(status_code=404, detail="世界观结果不存在")
    _ = await verify_project_access(world_result.project_id, user_id, db)
    return world_result


def _active_world_snapshot(project_id: str, session: Session) -> ProjectWorldSnapshot:
    project = session.execute(select(Project).where(Project.id == project_id)).scalar_one()
    return ProjectWorldSnapshot(
        project_id=project.id,
        world_time_period=project.world_time_period,
        world_location=project.world_location,
        world_atmosphere=project.world_atmosphere,
        world_rules=project.world_rules,
    )


def _result_response(result: WorldSettingResult | None) -> WorldSettingResultResponse | None:
    if result is None:
        return None
    return WorldSettingResultResponse.from_orm_result(result)


def _run_and_serialize_operation(
    session: Session,
    operation: Callable[[Session], WorldSettingOperationResult],
) -> _SerializedOperationResult:
    operation_result = operation(session)
    if not operation_result.changed:
        return _SerializedOperationResult(
            changed=False,
            reason=operation_result.reason,
            result=None,
            previous_result=None,
            active_world=None,
        )

    session.flush()
    operation_result.materialize_response_attributes()
    result_response = _result_response(operation_result.result)
    previous_response = _result_response(operation_result.previous_result)
    return _SerializedOperationResult(
        changed=True,
        reason=operation_result.reason,
        result=result_response,
        previous_result=previous_response,
        active_world=_active_world_snapshot(operation_result.result.project_id, session),
    )


async def _operation_response(
    *,
    result_id: str,
    user_id: str,
    db: AsyncSession,
    operation: Callable[[Session], WorldSettingOperationResult],
    failure_code: str,
    failure_message: str,
) -> WorldSettingResultOperationResponse:
    _ = await _get_result_for_user(result_id, user_id, db)
    operation_result = await db.run_sync(lambda session: _run_and_serialize_operation(session, operation))
    if not operation_result.changed:
        await db.rollback()
        _structured_error(
            400,
            code=failure_code,
            message=operation_result.reason or failure_message,
        )
    await db.commit()
    if operation_result.result is None or operation_result.active_world is None:
        _structured_error(500, code="world_result_operation_response_failed", message="世界观结果响应构建失败")
    return WorldSettingResultOperationResponse(
        changed=True,
        reason=operation_result.reason,
        result=operation_result.result,
        previous_result=operation_result.previous_result,
        active_world=operation_result.active_world,
    )


@router.get("", response_model=WorldSettingResultListResponse, summary="列出世界观结果")
async def list_world_setting_results(
    request: Request,
    project_id: str = Query(..., description="项目ID"),
    status: WorldSettingResultStatus | None = Query(None, description="结果状态"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> WorldSettingResultListResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(project_id, user_id, db)
    filters = [WorldSettingResult.project_id == project_id]
    if status is not None:
        filters.append(WorldSettingResult.status == status)

    count_result = await db.execute(select(func.count(WorldSettingResult.id)).where(*filters))
    result = await db.execute(
        select(WorldSettingResult)
        .where(*filters)
        .order_by(WorldSettingResult.created_at.desc(), WorldSettingResult.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return WorldSettingResultListResponse(
        total=count_result.scalar_one(),
        items=[WorldSettingResultResponse.model_validate(item) for item in result.scalars().all()],
    )


@router.get("/{result_id}", response_model=WorldSettingResultResponse, summary="获取世界观结果")
async def get_world_setting_result(
    result_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorldSettingResultResponse:
    user_id = _current_user_id(request)
    return WorldSettingResultResponse.model_validate(await _get_result_for_user(result_id, user_id, db))


@router.post("/{result_id}/accept", response_model=WorldSettingResultOperationResponse, summary="接受世界观结果")
async def accept_world_setting_result(
    result_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorldSettingResultOperationResponse:
    user_id = _current_user_id(request)
    return await _operation_response(
        result_id=result_id,
        user_id=user_id,
        db=db,
        operation=lambda session: WorldSettingResultService(session).accept_result(result_id, accepted_by=user_id),
        failure_code="world_result_accept_failed",
        failure_message="世界观结果接受失败",
    )


@router.post("/{result_id}/reject", response_model=WorldSettingResultOperationResponse, summary="拒绝世界观结果")
async def reject_world_setting_result(
    result_id: str,
    payload: WorldSettingRejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorldSettingResultOperationResponse:
    _ = payload
    user_id = _current_user_id(request)
    return await _operation_response(
        result_id=result_id,
        user_id=user_id,
        db=db,
        operation=lambda session: WorldSettingResultService(session).reject_result(result_id),
        failure_code="world_result_reject_failed",
        failure_message="世界观结果拒绝失败",
    )


@router.post("/{result_id}/rollback", response_model=WorldSettingResultOperationResponse, summary="回滚世界观结果")
async def rollback_world_setting_result(
    result_id: str,
    payload: WorldSettingRollbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorldSettingResultOperationResponse:
    _ = payload
    user_id = _current_user_id(request)
    return await _operation_response(
        result_id=result_id,
        user_id=user_id,
        db=db,
        operation=lambda session: WorldSettingResultService(session).rollback_result(result_id, actor_user_id=user_id),
        failure_code="world_result_rollback_failed",
        failure_message="世界观结果回滚失败",
    )
