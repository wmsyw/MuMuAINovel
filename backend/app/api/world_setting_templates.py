"""Reusable world-setting template APIs."""
from __future__ import annotations

import re
from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import verify_project_access
from app.database import get_db
from app.models.world_setting_template import WorldSettingTemplate
from app.schemas.world_setting_template import (
    ProjectWorldSettingData,
    WorldSettingApplyTemplateRequest,
    WorldSettingApplyTemplateResponse,
    WorldSettingFieldDefinition,
    WorldSettingTemplateListResponse,
    WorldSettingTemplateResponse,
)
from app.services.world_setting_data_service import (
    LEGACY_FIELD_MAP,
    WorldSettingDataError,
    normalize_world_setting_values,
)

router = APIRouter(prefix="/world-setting", tags=["世界设定模板"])
_FIELD_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _template_response(template: WorldSettingTemplate) -> WorldSettingTemplateResponse:
    definitions = {
        key: WorldSettingFieldDefinition.model_validate(value)
        for key, value in (template.field_definitions or {}).items()
    }
    return WorldSettingTemplateResponse(
        id=template.id,
        name=template.name,
        category=template.category,
        fields=definitions,
        example_data=template.example_data or {},
        is_system=bool(template.is_system),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


async def _get_visible_template(template_id: str, user_id: str, db: AsyncSession) -> WorldSettingTemplate:
    result = await db.execute(
        select(WorldSettingTemplate).where(
            WorldSettingTemplate.id == template_id,
            or_(WorldSettingTemplate.is_system.is_(True), WorldSettingTemplate.user_id == user_id),
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="世界设定模板不存在")
    return template


def _normalize_values(
    definitions: Mapping[str, WorldSettingFieldDefinition],
    values: Mapping[str, object],
) -> dict[str, object]:
    try:
        return normalize_world_setting_values(definitions, values, require_required=True)
    except WorldSettingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc




@router.get("/templates", response_model=WorldSettingTemplateListResponse, summary="获取世界设定模板")
async def list_world_setting_templates(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorldSettingTemplateListResponse:
    user_id = _current_user_id(request)
    result = await db.execute(
        select(WorldSettingTemplate)
        .where(or_(WorldSettingTemplate.is_system.is_(True), WorldSettingTemplate.user_id == user_id))
        .order_by(WorldSettingTemplate.is_system.desc(), WorldSettingTemplate.category, WorldSettingTemplate.name)
    )
    templates = list(result.scalars().all())
    return WorldSettingTemplateListResponse(total=len(templates), items=[_template_response(item) for item in templates])


@router.get("/templates/{template_id}", response_model=WorldSettingTemplateResponse, summary="获取世界设定模板详情")
async def get_world_setting_template(
    template_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorldSettingTemplateResponse:
    return _template_response(await _get_visible_template(template_id, _current_user_id(request), db))


@router.post("/apply-template", response_model=WorldSettingApplyTemplateResponse, summary="应用世界设定模板到项目")
async def apply_world_setting_template(
    payload: WorldSettingApplyTemplateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorldSettingApplyTemplateResponse:
    user_id = _current_user_id(request)
    project = await verify_project_access(payload.project_id, user_id, db)
    template = await _get_visible_template(payload.template_id, user_id, db)

    template_fields = {
        key: WorldSettingFieldDefinition.model_validate(value)
        for key, value in (template.field_definitions or {}).items()
    }
    for key in payload.custom_fields:
        if not _FIELD_KEY_PATTERN.fullmatch(key):
            raise HTTPException(status_code=422, detail=f"自定义字段键不合法: {key}")
    definitions = {
        key: WorldSettingFieldDefinition.model_validate(value)
        for key, value in {**template_fields, **payload.custom_fields}.items()
    }
    source_values = {**(template.example_data or {}), **payload.values}
    values = _normalize_values(definitions, source_values)

    world_data = ProjectWorldSettingData(
        template_id=template.id,
        template_name=template.name,
        fields=definitions,
        values=values,
    )
    project.world_setting_data = world_data.model_dump(mode="json")
    for field_key, project_attribute in LEGACY_FIELD_MAP.items():
        value = values.get(field_key)
        setattr(project, project_attribute, value if isinstance(value, str) else None)

    await db.commit()
    await db.refresh(project)
    return WorldSettingApplyTemplateResponse(
        project_id=project.id,
        template=_template_response(template),
        world_setting_data=world_data,
    )
