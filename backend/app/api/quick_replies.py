"""Quick replies / safe snippet API."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false, reportCallInDefaultInitializer=false, reportMissingTypeArgument=false

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import feature_flags
from app.api.common import verify_project_access
from app.database import get_db
from app.schemas.quick_reply import (
    QuickReplyApplyRequest,
    QuickReplyApplyResponse,
    QuickReplyCreate,
    QuickReplyListResponse,
    QuickReplyResponse,
    QuickReplyUpdate,
)
from app.services.creative_session_service import CreativeSessionService
from app.services.quick_reply_service import QuickReplyService, QuickReplyValidationError

router = APIRouter(prefix="/quick-replies", tags=["快捷回复"])


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("quick_actions_enabled"):
        raise HTTPException(status_code=404, detail="快捷操作功能未启用")


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _bad_request_from_validation(exc: QuickReplyValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


async def _get_reply_for_user(reply_id: str, user_id: str, db: AsyncSession):
    reply = await QuickReplyService.get_reply(db=db, reply_id=reply_id, user_id=user_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="快捷回复不存在")
    await verify_project_access(reply.project_id, user_id, db)
    return reply


@router.post("/projects/{project_id}", response_model=QuickReplyResponse, summary="创建快捷回复安全片段")
async def create_quick_reply(
    project_id: str,
    payload: QuickReplyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        reply = await QuickReplyService.create_reply(
            db=db,
            project_id=project_id,
            user_id=user_id,
            label=payload.label,
            action_type=payload.action_type,
            snippet=payload.snippet,
            sort_order=payload.sort_order,
            enabled=payload.enabled,
        )
    except QuickReplyValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return QuickReplyService.reply_dict(reply)


@router.get("/projects/{project_id}", response_model=QuickReplyListResponse, summary="列出项目快捷回复")
async def list_quick_replies(
    project_id: str,
    request: Request,
    enabled: bool | None = Query(None, description="按启用状态筛选"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    total, replies = await QuickReplyService.list_replies(
        db=db,
        project_id=project_id,
        user_id=user_id,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": [QuickReplyService.reply_dict(reply) for reply in replies]}


@router.get("/{reply_id}", response_model=QuickReplyResponse, summary="获取快捷回复")
async def get_quick_reply(
    reply_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    reply = await _get_reply_for_user(reply_id, user_id, db)
    return QuickReplyService.reply_dict(reply)


@router.put("/{reply_id}", response_model=QuickReplyResponse, summary="更新快捷回复")
async def update_quick_reply(
    reply_id: str,
    payload: QuickReplyUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    reply = await _get_reply_for_user(reply_id, user_id, db)
    try:
        updated = await QuickReplyService.update_reply(
            db=db,
            reply=reply,
            updates=payload.model_dump(exclude_unset=True, exclude={"user_id"}),
        )
    except QuickReplyValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return QuickReplyService.reply_dict(updated)


@router.delete("/{reply_id}", summary="删除快捷回复")
async def delete_quick_reply(
    reply_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    _ensure_enabled()
    user_id = _current_user_id(request)
    reply = await _get_reply_for_user(reply_id, user_id, db)
    await QuickReplyService.delete_reply(db=db, reply=reply)
    return {"deleted": True}


@router.post("/{reply_id}/apply", response_model=QuickReplyApplyResponse, summary="将快捷回复安全片段写入创作会话")
async def apply_quick_reply_snippet(
    reply_id: str,
    payload: QuickReplyApplyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    reply = await _get_reply_for_user(reply_id, user_id, db)
    session = await CreativeSessionService.get_session(db=db, session_id=payload.session_id, user_id=user_id)
    if session is None or session.project_id != reply.project_id:
        raise HTTPException(status_code=404, detail="创作会话不存在")
    await verify_project_access(session.project_id, user_id, db)
    try:
        message, trace = await QuickReplyService.apply_to_creative_session(
            db=db,
            reply=reply,
            session=session,
            user_id=user_id,
        )
    except QuickReplyValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return {
        "quick_reply": QuickReplyService.reply_dict(reply),
        **trace,
        "emitted_message": CreativeSessionService.message_dict(message),
    }
