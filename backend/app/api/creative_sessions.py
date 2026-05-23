"""创作会话 API。"""

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false, reportCallInDefaultInitializer=false, reportUnusedCallResult=false

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import feature_flags
from app.api.common import verify_project_access
from app.database import get_db
from app.schemas.creative_session import (
    CreativeSessionCreate,
    CreativeSessionDetailResponse,
    CreativeSessionListResponse,
    CreativeSessionMessageCreate,
    CreativeSessionMessageResponse,
    CreativeSessionResponse,
    CreativeSessionSearchResponse,
    CreativeSessionSearchResult,
)
from app.services.creative_session_service import CreativeSessionService

router = APIRouter(prefix="/creative-sessions", tags=["创作会话"])


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("creative_sessions_enabled"):
        raise HTTPException(status_code=404, detail="创作会话功能未启用")


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


@router.post("/projects/{project_id}", response_model=CreativeSessionResponse, summary="创建创作会话")
async def create_creative_session(
    project_id: str,
    payload: CreativeSessionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """创建项目内创作会话。"""
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    session = await CreativeSessionService.create_session(
        db=db,
        project_id=project_id,
        user_id=user_id,
        title=payload.title,
        metadata=payload.metadata,
    )
    return CreativeSessionService.session_dict(session)


@router.get("/projects/{project_id}", response_model=CreativeSessionListResponse, summary="获取项目创作会话")
async def list_creative_sessions(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取项目内创作会话列表。"""
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    sessions = await CreativeSessionService.list_sessions(db=db, project_id=project_id, user_id=user_id)
    return {"total": len(sessions), "items": [CreativeSessionService.session_dict(item) for item in sessions]}


@router.get("/projects/{project_id}/search", response_model=CreativeSessionSearchResponse, summary="搜索创作会话记录")
async def search_creative_session_messages(
    project_id: str,
    request: Request,
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """在当前用户的项目创作会话消息中搜索文本。"""
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    rows = await CreativeSessionService.search_messages(
        db=db,
        project_id=project_id,
        user_id=user_id,
        query=query,
        limit=limit,
    )
    items = [
        CreativeSessionSearchResult(
            session_id=session.id,
            session_title=session.title,
            message_id=message.id,
            project_id=message.project_id,
            user_id=message.user_id,
            role=message.role,
            content=message.content,
            position=message.position,
            created_at=message.created_at,
        )
        for message, session in rows
    ]
    return {"query": query, "total": len(items), "items": items}


@router.get("/{session_id}", response_model=CreativeSessionDetailResponse, summary="重新打开创作会话")
async def get_creative_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取创作会话及其消息。"""
    _ensure_enabled()
    user_id = _current_user_id(request)
    session = await CreativeSessionService.get_session(db=db, session_id=session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=404, detail="创作会话不存在")
    await verify_project_access(session.project_id, user_id, db)
    messages = await CreativeSessionService.list_messages(db=db, session_id=session_id, user_id=user_id)
    data = CreativeSessionService.session_dict(session)
    data["messages"] = [CreativeSessionService.message_dict(message) for message in messages]
    return data


@router.post("/{session_id}/messages", response_model=CreativeSessionMessageResponse, summary="追加创作会话消息")
async def append_creative_session_message(
    session_id: str,
    payload: CreativeSessionMessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """追加会话消息，不触发章节/世界观/记忆等自动写入。"""
    _ensure_enabled()
    user_id = _current_user_id(request)
    session = await CreativeSessionService.get_session(db=db, session_id=session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=404, detail="创作会话不存在")
    await verify_project_access(session.project_id, user_id, db)
    message = await CreativeSessionService.append_message(
        db=db,
        session=session,
        user_id=user_id,
        role=payload.role,
        content=payload.content,
        metadata=payload.metadata,
    )
    return CreativeSessionService.message_dict(message)
