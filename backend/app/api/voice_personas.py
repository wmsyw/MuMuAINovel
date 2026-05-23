"""Narrator voice persona API."""

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false, reportCallInDefaultInitializer=false, reportMissingTypeArgument=false

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import feature_flags
from app.api.common import verify_project_access
from app.database import get_db
from app.models.creative_session import CreativeSession
from app.models.voice_persona import VoicePersona
from app.schemas.voice_persona import (
    VoicePersonaCreate,
    VoicePersonaListResponse,
    VoicePersonaPromptPreviewRequest,
    VoicePersonaPromptPreviewResponse,
    VoicePersonaResponse,
    VoicePersonaUpdate,
)
from app.services.creative_session_service import CreativeSessionService
from app.services.prompt_service import PromptService
from app.services.voice_persona_service import VoicePersonaService, VoicePersonaValidationError

router = APIRouter(prefix="/voice-personas", tags=["旁白声音画像"])


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("voice_personas_enabled"):
        raise HTTPException(status_code=404, detail="旁白声音画像功能未启用")


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _bad_request_from_validation(exc: VoicePersonaValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


async def _validate_session_scope(
    *,
    db: AsyncSession,
    session_id: str | None,
    project_id: str,
    user_id: str,
) -> CreativeSession | None:
    if not session_id:
        return None
    session = await CreativeSessionService.get_session(db=db, session_id=session_id, user_id=user_id)
    if session is None or session.project_id != project_id:
        raise HTTPException(status_code=404, detail="创作会话不存在")
    return session


async def _get_persona_for_user(*, db: AsyncSession, persona_id: str, user_id: str) -> VoicePersona:
    persona = await VoicePersonaService.get_persona(db=db, persona_id=persona_id, user_id=user_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="声音画像不存在")
    await verify_project_access(persona.project_id, user_id, db)
    return persona


async def _get_persona_for_project(
    *,
    db: AsyncSession,
    persona_id: str,
    project_id: str,
    user_id: str,
) -> VoicePersona:
    persona = await VoicePersonaService.get_persona(db=db, persona_id=persona_id, project_id=project_id, user_id=user_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="声音画像不存在")
    return persona


@router.post("/projects/{project_id}", response_model=VoicePersonaResponse, summary="创建项目/会话旁白声音画像")
async def create_voice_persona(
    project_id: str,
    payload: VoicePersonaCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    await _validate_session_scope(db=db, session_id=payload.session_id, project_id=project_id, user_id=user_id)
    try:
        persona = await VoicePersonaService.create_persona(
            db=db,
            project_id=project_id,
            user_id=user_id,
            session_id=payload.session_id,
            name=payload.name,
            tone=payload.tone,
            style=payload.style,
            point_of_view=payload.point_of_view,
            constraints=payload.constraints,
            sort_order=payload.sort_order,
            enabled=payload.enabled,
        )
    except VoicePersonaValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return VoicePersonaService.persona_dict(persona)


@router.get("/projects/{project_id}", response_model=VoicePersonaListResponse, summary="列出项目/会话旁白声音画像")
async def list_voice_personas(
    project_id: str,
    request: Request,
    session_id: str | None = Query(None, description="可选：包含指定创作会话的会话级画像"),
    enabled: bool | None = Query(None, description="按启用状态筛选"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    await _validate_session_scope(db=db, session_id=session_id, project_id=project_id, user_id=user_id)
    total, personas = await VoicePersonaService.list_personas(
        db=db,
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": [VoicePersonaService.persona_dict(persona) for persona in personas]}


@router.get("/{persona_id}", response_model=VoicePersonaResponse, summary="获取旁白声音画像")
async def get_voice_persona(
    persona_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    persona = await _get_persona_for_user(db=db, persona_id=persona_id, user_id=user_id)
    return VoicePersonaService.persona_dict(persona)


@router.put("/{persona_id}", response_model=VoicePersonaResponse, summary="更新旁白声音画像")
async def update_voice_persona(
    persona_id: str,
    payload: VoicePersonaUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    persona = await _get_persona_for_user(db=db, persona_id=persona_id, user_id=user_id)
    updates = payload.model_dump(exclude_unset=True, exclude={"user_id"})
    if "session_id" in updates:
        await _validate_session_scope(db=db, session_id=updates["session_id"], project_id=persona.project_id, user_id=user_id)
    try:
        updated = await VoicePersonaService.update_persona(db=db, persona=persona, updates=updates)
    except VoicePersonaValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return VoicePersonaService.persona_dict(updated)


@router.delete("/{persona_id}", summary="删除旁白声音画像")
async def delete_voice_persona(
    persona_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    _ensure_enabled()
    user_id = _current_user_id(request)
    persona = await _get_persona_for_user(db=db, persona_id=persona_id, user_id=user_id)
    await VoicePersonaService.delete_persona(db=db, persona=persona)
    return {"deleted": True}


@router.post(
    "/projects/{project_id}/prompt-preview",
    response_model=VoicePersonaPromptPreviewResponse,
    summary="预览旁白声音画像提示词追踪",
)
async def preview_voice_persona_prompt_trace(
    project_id: str,
    payload: VoicePersonaPromptPreviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    await _validate_session_scope(db=db, session_id=payload.session_id, project_id=project_id, user_id=user_id)
    persona = await _get_persona_for_project(db=db, persona_id=payload.persona_id, project_id=project_id, user_id=user_id)
    if persona.session_id and persona.session_id != payload.session_id:
        raise HTTPException(status_code=404, detail="声音画像不存在")
    if not persona.enabled:
        raise HTTPException(status_code=400, detail="声音画像已停用")

    trace = PromptService.build_voice_persona_prompt_trace(
        persona,
        project_id=project_id,
        session_id=payload.session_id,
    )
    preview_prompt = PromptService.apply_voice_persona_prompt_trace(
        payload.base_prompt,
        trace,
        injection_enabled=payload.injection_enabled,
    )
    return {
        "project_id": project_id,
        "session_id": payload.session_id,
        "trace": trace,
        "preview_prompt": preview_prompt,
    }
