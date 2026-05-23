"""Lorebook / world-info API."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false, reportCallInDefaultInitializer=false, reportMissingTypeArgument=false, reportUnusedCallResult=false

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import verify_project_access
from app.database import get_db
from app.schemas.lorebook import (
    LorebookEntryCreate,
    LorebookEntryListResponse,
    LorebookEntryResponse,
    LorebookEntryUpdate,
    LorebookPromptPreviewResponse,
    LorebookSelectionRequest,
    LorebookSelectionResponse,
)
from app.services.lorebook_service import LorebookService
from app.services.prompt_service import PromptService

router = APIRouter(prefix="/lorebook", tags=["Lorebook"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


async def _get_entry_for_user(entry_id: str, user_id: str, db: AsyncSession):
    entry = await LorebookService.get_entry(db=db, entry_id=entry_id, user_id=user_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Lorebook条目不存在")
    await verify_project_access(entry.project_id, user_id, db)
    return entry


@router.post("/projects/{project_id}", response_model=LorebookEntryResponse, summary="创建Lorebook条目")
async def create_lorebook_entry(
    project_id: str,
    payload: LorebookEntryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    entry = await LorebookService.create_entry(
        db=db,
        project_id=project_id,
        user_id=user_id,
        title=payload.title,
        content=payload.content,
        activation_keys=payload.activation_keys,
        priority=payload.priority,
        enabled=payload.enabled,
        source_type=payload.source_type,
        metadata=payload.metadata,
    )
    return LorebookService.entry_dict(entry)


@router.get("/projects/{project_id}", response_model=LorebookEntryListResponse, summary="列出Lorebook条目")
async def list_lorebook_entries(
    project_id: str,
    request: Request,
    enabled: bool | None = Query(None, description="按启用状态筛选"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    total, entries = await LorebookService.list_entries(
        db=db,
        project_id=project_id,
        user_id=user_id,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": [LorebookService.entry_dict(entry) for entry in entries]}


@router.post("/projects/{project_id}/select", response_model=LorebookSelectionResponse, summary="预览Lorebook确定性选择")
async def select_lorebook_entries(
    project_id: str,
    payload: LorebookSelectionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    selection = await LorebookService.select_for_project(
        db=db,
        project_id=project_id,
        user_id=user_id,
        activation_text=payload.activation_text,
        max_chars=payload.max_chars,
        max_tokens=payload.max_tokens,
        chars_per_token=payload.chars_per_token,
    )
    return LorebookService.selection_dict(selection)


@router.post(
    "/projects/{project_id}/prompt-preview",
    response_model=LorebookPromptPreviewResponse,
    summary="预览Lorebook提示词注入追踪",
)
async def preview_lorebook_prompt_trace(
    project_id: str,
    payload: LorebookSelectionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    selection = await LorebookService.select_for_project(
        db=db,
        project_id=project_id,
        user_id=user_id,
        activation_text=payload.activation_text,
        max_chars=payload.max_chars,
        max_tokens=payload.max_tokens,
        chars_per_token=payload.chars_per_token,
    )
    return {
        "project_id": project_id,
        "trace": PromptService.build_lorebook_prompt_trace(
            selection,
            chars_per_token=payload.chars_per_token,
        ),
    }


@router.get("/{entry_id}", response_model=LorebookEntryResponse, summary="获取Lorebook条目")
async def get_lorebook_entry(
    entry_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = _current_user_id(request)
    entry = await _get_entry_for_user(entry_id, user_id, db)
    return LorebookService.entry_dict(entry)


@router.put("/{entry_id}", response_model=LorebookEntryResponse, summary="更新Lorebook条目")
async def update_lorebook_entry(
    entry_id: str,
    payload: LorebookEntryUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_id = _current_user_id(request)
    entry = await _get_entry_for_user(entry_id, user_id, db)
    update_payload = payload.model_dump(exclude_unset=True, exclude={"user_id"})
    updated = await LorebookService.update_entry(db=db, entry=entry, updates=update_payload)
    return LorebookService.entry_dict(updated)


@router.delete("/{entry_id}", summary="删除Lorebook条目")
async def delete_lorebook_entry(
    entry_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    user_id = _current_user_id(request)
    entry = await _get_entry_for_user(entry_id, user_id, db)
    await LorebookService.delete_entry(db=db, entry=entry)
    return {"deleted": True}
