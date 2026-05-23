"""Project-scoped safe local asset API."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import feature_flags
from app.api.common import verify_project_access
from app.database import get_db
from app.schemas.project_asset import ProjectAssetListResponse, ProjectAssetResponse, ProjectAssetType
from app.services.project_asset_service import (
    MAX_ASSET_UPLOAD_BYTES,
    ProjectAssetValidationError,
    project_asset_service,
    validate_asset_type,
    validate_original_filename,
)


router = APIRouter(prefix="/projects/{project_id}/assets", tags=["本地资源"])


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("local_assets_enabled"):
        raise HTTPException(status_code=404, detail="本地资源功能未启用")


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _bad_request_from_validation(exc: ProjectAssetValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post("", response_model=ProjectAssetResponse, summary="上传项目本地资源")
async def upload_project_asset(
    project_id: str,
    request: Request,
    asset_type: ProjectAssetType = Form(...),
    display_name: str | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        validate_asset_type(asset_type)
        validate_original_filename(file.filename)
        raw_bytes = await file.read(MAX_ASSET_UPLOAD_BYTES + 1)
        asset = await project_asset_service.create_asset(
            db=db,
            project_id=project_id,
            user_id=user_id,
            asset_type=asset_type,
            display_name=display_name,
            original_filename=file.filename,
            content_type=file.content_type,
            raw_bytes=raw_bytes,
        )
    except ProjectAssetValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return project_asset_service.asset_dict(asset)


@router.get("", response_model=ProjectAssetListResponse, summary="列出项目本地资源")
async def list_project_assets(
    project_id: str,
    request: Request,
    asset_type: ProjectAssetType | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        total, items = await project_asset_service.list_assets(
            db=db,
            project_id=project_id,
            user_id=user_id,
            asset_type=asset_type,
            limit=limit,
            offset=offset,
        )
    except ProjectAssetValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return {"total": total, "items": [project_asset_service.asset_dict(item) for item in items]}


@router.get("/{asset_id}/file", summary="读取项目本地资源文件")
async def get_project_asset_file(
    project_id: str,
    asset_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        asset = await project_asset_service.get_asset(db=db, asset_id=asset_id, project_id=project_id, user_id=user_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="本地资源不存在")
        file_path = project_asset_service.resolve_asset_path(asset)
    except ProjectAssetValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="本地资源文件不存在")
    return FileResponse(path=file_path, media_type=asset.mime_type)


@router.delete("/{asset_id}", summary="删除项目本地资源")
async def delete_project_asset(
    project_id: str,
    asset_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        deleted = await project_asset_service.delete_asset(db=db, asset_id=asset_id, project_id=project_id, user_id=user_id)
    except ProjectAssetValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="本地资源不存在")
    return {"deleted": True}
