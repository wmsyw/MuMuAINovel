"""金手指管理API"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import verify_project_access
from app.database import get_db
from app.logger import get_logger
from app.schemas.goldfinger import (
    GoldfingerCreate,
    GoldfingerExportPayload,
    GoldfingerHistoryListResponse,
    GoldfingerImportDryRunResult,
    GoldfingerImportPayload,
    GoldfingerImportResult,
    GoldfingerListResponse,
    GoldfingerResponse,
    GoldfingerUpdate,
)
from app.services.goldfinger_service import GoldfingerService

router = APIRouter(prefix="/goldfingers", tags=["金手指管理"])
logger = get_logger(__name__)


def _user_id(request: Request) -> str | None:
    return getattr(request.state, "user_id", None)


@router.get("/project/{project_id}", response_model=GoldfingerListResponse, summary="获取项目金手指列表")
async def list_project_goldfingers(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取指定项目的所有金手指。"""
    user_id = _user_id(request)
    await verify_project_access(project_id, user_id, db)

    rows = await GoldfingerService.list_goldfingers(project_id, db)
    return {"total": len(rows), "items": [GoldfingerService.response_dict(row) for row in rows]}


@router.post("/project/{project_id}", response_model=GoldfingerResponse, summary="创建金手指")
async def create_project_goldfinger(
    project_id: str,
    payload: GoldfingerCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """手动创建金手指，并写入 manual 历史事件。"""
    user_id = _user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        goldfinger = await GoldfingerService.create_goldfinger(
            project_id=project_id,
            data=payload.model_dump(exclude_unset=True),
            user_id=str(user_id),
            db=db,
            source="manual",
            history_source_type="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(f"创建金手指成功：{goldfinger.name} (ID: {goldfinger.id})")
    return GoldfingerService.response_dict(goldfinger)


@router.get("/project/{project_id}/export", response_model=GoldfingerExportPayload, summary="导出项目金手指")
async def export_project_goldfingers(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """导出项目金手指卡片，版本固定为 goldfinger-card.v1。"""
    user_id = _user_id(request)
    await verify_project_access(project_id, user_id, db)
    return await GoldfingerService.export_project(project_id, db)


@router.post("/project/{project_id}/import/dry-run", response_model=GoldfingerImportDryRunResult, summary="金手指导入 dry-run")
async def dry_run_import_project_goldfingers(
    project_id: str,
    payload: GoldfingerImportPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """验证导入载荷并报告规范化名称冲突，不写入任何正式或历史数据。"""
    user_id = _user_id(request)
    await verify_project_access(project_id, user_id, db)
    return await GoldfingerService.dry_run_import(project_id=project_id, payload=payload, db=db)


@router.post("/project/{project_id}/import", response_model=GoldfingerImportResult, summary="导入项目金手指")
async def import_project_goldfingers(
    project_id: str,
    payload: GoldfingerImportPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """导入已通过 dry-run 的金手指卡片，并写入 import 历史事件。"""
    user_id = _user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        return await GoldfingerService.import_project(
            project_id=project_id,
            payload=payload,
            user_id=str(user_id),
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{goldfinger_id}/history", response_model=GoldfingerHistoryListResponse, summary="获取金手指历史")
async def get_goldfinger_history(
    goldfinger_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取金手指历史事件。"""
    goldfinger = await GoldfingerService.get_goldfinger(goldfinger_id, db)
    if not goldfinger:
        raise HTTPException(status_code=404, detail="金手指不存在")
    user_id = _user_id(request)
    await verify_project_access(goldfinger.project_id, user_id, db)
    rows = await GoldfingerService.list_history(goldfinger_id, db)
    return {"total": len(rows), "items": [GoldfingerService.history_dict(row) for row in rows]}


@router.get("/{goldfinger_id}", response_model=GoldfingerResponse, summary="获取金手指详情")
async def get_goldfinger(
    goldfinger_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """根据 ID 获取金手指详情。"""
    goldfinger = await GoldfingerService.get_goldfinger(goldfinger_id, db)
    if not goldfinger:
        raise HTTPException(status_code=404, detail="金手指不存在")
    user_id = _user_id(request)
    await verify_project_access(goldfinger.project_id, user_id, db)
    return GoldfingerService.response_dict(goldfinger)


@router.put("/{goldfinger_id}", response_model=GoldfingerResponse, summary="更新金手指")
async def update_goldfinger(
    goldfinger_id: str,
    payload: GoldfingerUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """更新金手指，并为实际变化写入 manual 历史事件。"""
    goldfinger = await GoldfingerService.get_goldfinger(goldfinger_id, db)
    if not goldfinger:
        raise HTTPException(status_code=404, detail="金手指不存在")
    user_id = _user_id(request)
    await verify_project_access(goldfinger.project_id, user_id, db)
    try:
        updated = await GoldfingerService.update_goldfinger(
            goldfinger=goldfinger,
            data=payload.model_dump(exclude_unset=True),
            user_id=str(user_id),
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(f"更新金手指成功：{updated.name} (ID: {goldfinger_id})")
    return GoldfingerService.response_dict(updated)


@router.delete("/{goldfinger_id}", summary="删除金手指")
async def delete_goldfinger(
    goldfinger_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """硬删除金手指，行为与现有角色/职业/组织实体模块保持一致。"""
    goldfinger = await GoldfingerService.get_goldfinger(goldfinger_id, db)
    if not goldfinger:
        raise HTTPException(status_code=404, detail="金手指不存在")
    user_id = _user_id(request)
    await verify_project_access(goldfinger.project_id, user_id, db)
    name = goldfinger.name
    await GoldfingerService.delete_goldfinger(goldfinger, db)
    logger.info(f"删除金手指成功：{name} (ID: {goldfinger_id})")
    return {"message": "金手指删除成功", "id": goldfinger_id}
