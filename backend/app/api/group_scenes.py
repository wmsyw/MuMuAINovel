"""Bounded group scene authoring API."""

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false, reportCallInDefaultInitializer=false, reportMissingTypeArgument=false

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import feature_flags
from app.api.common import verify_project_access
from app.database import get_db
from app.models.group_scene import GroupScene
from app.schemas.group_scene import GroupSceneDraftRequest, GroupSceneListResponse, GroupSceneResponse
from app.services.group_scene_service import GroupSceneService, GroupSceneValidationError

router = APIRouter(prefix="/group-scenes", tags=["群像场景"])


def _ensure_enabled() -> None:
    if not feature_flags.is_enabled("group_scene_simulation_enabled"):
        raise HTTPException(status_code=404, detail="群像场景功能未启用")


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _bad_request_from_validation(exc: GroupSceneValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


async def _get_scene_for_user(*, db: AsyncSession, scene_id: str, user_id: str) -> GroupScene:
    scene = await GroupSceneService.get_scene(db=db, scene_id=scene_id, user_id=user_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="群像场景不存在")
    await verify_project_access(scene.project_id, user_id, db)
    return scene


@router.post("/projects/{project_id}/draft", response_model=GroupSceneResponse, summary="创建群像场景写作草稿")
async def draft_group_scene(
    project_id: str,
    payload: GroupSceneDraftRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    project = await verify_project_access(project_id, user_id, db)
    try:
        scene = await GroupSceneService.create_scene(
            db=db,
            project=project,
            user_id=user_id,
            title=payload.title,
            scenario=payload.scenario,
            participant_character_ids=payload.participant_character_ids,
            selected_voice_persona_id=payload.selected_voice_persona_id,
            selected_lore_ids=payload.selected_lore_ids,
            prompt_context=payload.prompt_context,
            draft_text=payload.draft_text,
        )
    except GroupSceneValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return GroupSceneService.scene_dict(scene)


@router.get("/projects/{project_id}", response_model=GroupSceneListResponse, summary="列出项目群像场景")
async def list_group_scenes(
    project_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    total, scenes = await GroupSceneService.list_scenes(db=db, project_id=project_id, user_id=user_id, limit=limit, offset=offset)
    return {"total": total, "items": [GroupSceneService.scene_dict(scene) for scene in scenes]}


@router.get("/{scene_id}", response_model=GroupSceneResponse, summary="获取群像场景")
async def get_group_scene(scene_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    _ensure_enabled()
    user_id = _current_user_id(request)
    scene = await _get_scene_for_user(db=db, scene_id=scene_id, user_id=user_id)
    return GroupSceneService.scene_dict(scene)


@router.delete("/{scene_id}", summary="删除群像场景")
async def delete_group_scene(scene_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    _ensure_enabled()
    user_id = _current_user_id(request)
    scene = await _get_scene_for_user(db=db, scene_id=scene_id, user_id=user_id)
    await GroupSceneService.delete_scene(db=db, scene=scene)
    return {"deleted": True}
