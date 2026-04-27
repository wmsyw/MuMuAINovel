"""角色管理API"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
from typing import AsyncGenerator

from app.database import get_db
from app.utils.sse_response import SSEResponse, create_sse_response, WizardProgressTracker
from app.models.character import Character
from app.models.generation_history import GenerationHistory
from app.models.relationship import EntityRelationship, Organization, OrganizationEntity, OrganizationMember, RelationshipType
from app.schemas.character import (
    CharacterCreate,
    CharacterUpdate,
    CharacterResponse,
    CharacterListResponse,
    CharacterGenerateRequest
)
from app.services.ai_service import AIService
from app.services.entity_generation_policy_service import entity_generation_policy_service
from app.services.prompt_service import PromptService
from app.services.import_export_service import ImportExportService
from app.services.relationship_merge_service import RelationshipMergeService
from app.schemas.import_export import CharactersExportRequest, CharactersImportResult
from app.logger import get_logger
from app.api.settings import get_user_ai_service
from app.api.common import verify_project_access
from app.api.entity_compat import build_optional_entity_enrichment, candidate_policy_payload, normalized_name, safe_json_loads

router = APIRouter(prefix="/characters", tags=["角色管理"])
logger = get_logger(__name__)


async def _build_relationships_summary(character_id: str, project_id: str, db: AsyncSession) -> str:
    """从 entity_relationships 表构建角色关系摘要文本"""
    from sqlalchemy import or_
    
    # 查询该角色参与的所有关系
    rels_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.project_id == project_id,
            EntityRelationship.from_entity_type == "character",
            EntityRelationship.to_entity_type == "character",
            or_(
                EntityRelationship.from_entity_id == character_id,
                EntityRelationship.to_entity_id == character_id
            )
        )
    )
    rels = rels_result.scalars().all()
    
    if not rels:
        return ""
    
    # 收集所有相关角色ID
    related_ids = set()
    for r in rels:
        related_ids.add(r.character_from_id)
        related_ids.add(r.character_to_id)
    related_ids.discard(character_id)
    
    if not related_ids:
        return ""
    
    # 批量查询角色名称
    chars_result = await db.execute(
        select(Character.id, Character.name).where(Character.id.in_(related_ids))
    )
    name_map = {row.id: row.name for row in chars_result}
    
    # 构建摘要
    parts = []
    for r in rels:
        if r.character_from_id == character_id:
            target_name = name_map.get(r.character_to_id, "未知")
            rel_name = r.relationship_name or "相关"
        else:
            target_name = name_map.get(r.character_from_id, "未知")
            rel_name = r.relationship_name or "相关"
        parts.append(f"与{target_name}：{rel_name}")
    
    return "；".join(parts)


async def _build_org_members_summary(organization_entity_id: str, db: AsyncSession) -> str:
    """从 organization_members 表构建组织成员JSON字符串（与schema契约保持一致）"""

    # 查询该组织的所有成员（按职级倒序，保证展示顺序稳定）
    members_result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_entity_id == organization_entity_id)
        .order_by(OrganizationMember.rank.desc(), OrganizationMember.created_at)
    )
    members = members_result.scalars().all()
    if not members:
        return ""

    # 批量查询成员角色名称
    member_char_ids = [m.character_id for m in members]
    chars_result = await db.execute(
        select(Character.id, Character.name).where(Character.id.in_(member_char_ids))
    )
    name_map = {row.id: row.name for row in chars_result}

    # 返回 JSON 字符串数组，避免前端 JSON.parse 报错
    member_items = []
    for m in members:
        name = name_map.get(m.character_id, "未知")
        position = m.position or "成员"
        member_items.append(f"{name}（{position}）")

    return json.dumps(member_items, ensure_ascii=False)


async def _get_organization_entity(entity_id: str, db: AsyncSession) -> OrganizationEntity | None:
    """Resolve canonical org entity from current ID or legacy bridge identifiers."""
    result = await db.execute(select(OrganizationEntity).where(OrganizationEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity:
        return entity

    bridge_result = await db.execute(
        select(Organization).where(
            (Organization.id == entity_id)
            | (Organization.character_id == entity_id)
            | (Organization.organization_entity_id == entity_id)
        )
    )
    bridge = bridge_result.scalar_one_or_none()
    if bridge and bridge.organization_entity_id:
        result = await db.execute(select(OrganizationEntity).where(OrganizationEntity.id == bridge.organization_entity_id))
        return result.scalar_one_or_none()

    legacy_result = await db.execute(
        select(OrganizationEntity).where(
            (OrganizationEntity.legacy_character_id == entity_id) | (OrganizationEntity.legacy_organization_id == entity_id)
        )
    )
    return legacy_result.scalar_one_or_none()


async def _ensure_organization_bridge(org_entity: OrganizationEntity, db: AsyncSession) -> Organization:
    result = await db.execute(select(Organization).where(Organization.organization_entity_id == org_entity.id))
    bridge = result.scalar_one_or_none()
    if bridge:
        return bridge
    bridge = Organization(
        character_id=org_entity.legacy_character_id,
        project_id=org_entity.project_id,
        organization_entity_id=org_entity.id,
    )
    db.add(bridge)
    await db.flush()
    return bridge


async def _character_response_dict(
    character: Character,
    db: AsyncSession,
    request: Request | None = None,
    *,
    include_provenance: bool = False,
    include_aliases: bool = False,
    include_candidate_counts: bool = False,
    include_timeline: bool = False,
    include_policy_status: bool = False,
) -> dict:
    rel_summary = await _build_relationships_summary(character.id, character.project_id, db)
    data = {
        "id": character.id,
        "project_id": character.project_id,
        "name": character.name,
        "age": character.age,
        "gender": character.gender,
        "is_organization": False,
        "role_type": character.role_type,
        "personality": character.personality,
        "background": character.background,
        "appearance": character.appearance,
        "relationships": rel_summary,
        "organization_type": None,
        "organization_purpose": None,
        "organization_members": "",
        "traits": character.traits,
        "avatar_url": character.avatar_url,
        "created_at": character.created_at,
        "updated_at": character.updated_at,
        "power_level": None,
        "location": None,
        "motto": None,
        "color": None,
        "main_career_id": character.main_career_id,
        "main_career_stage": character.main_career_stage,
        "sub_careers": safe_json_loads(character.sub_careers),
        "status": character.status,
        "status_changed_chapter": character.status_changed_chapter,
        "current_state": character.current_state,
        "state_updated_chapter": character.state_updated_chapter,
    }
    if request is not None:
        data.update(await build_optional_entity_enrichment(
            db=db,
            request=request,
            project_id=character.project_id,
            entity_type="character",
            entity_id=character.id,
            include_provenance=include_provenance,
            include_aliases=include_aliases,
            include_candidate_counts=include_candidate_counts,
            include_timeline=include_timeline,
            include_policy_status=include_policy_status,
        ))
    return data


async def _organization_as_character_response_dict(
    org_entity: OrganizationEntity,
    db: AsyncSession,
    request: Request | None = None,
    *,
    include_provenance: bool = False,
    include_aliases: bool = False,
    include_candidate_counts: bool = False,
    include_timeline: bool = False,
    include_policy_status: bool = False,
) -> dict:
    data = {
        "id": org_entity.id,
        "project_id": org_entity.project_id,
        "name": org_entity.name,
        "age": None,
        "gender": None,
        "is_organization": True,
        "role_type": "organization",
        "personality": org_entity.personality,
        "background": org_entity.background,
        "appearance": None,
        "relationships": "",
        "organization_type": org_entity.organization_type,
        "organization_purpose": org_entity.organization_purpose,
        "organization_members": await _build_org_members_summary(org_entity.id, db),
        "traits": org_entity.traits,
        "avatar_url": org_entity.avatar_url,
        "created_at": org_entity.created_at,
        "updated_at": org_entity.updated_at,
        "power_level": org_entity.power_level,
        "location": org_entity.location,
        "motto": org_entity.motto,
        "color": org_entity.color,
        "main_career_id": None,
        "main_career_stage": None,
        "sub_careers": None,
        "status": org_entity.status,
        "status_changed_chapter": None,
        "current_state": org_entity.current_state,
        "state_updated_chapter": None,
    }
    if request is not None:
        data.update(await build_optional_entity_enrichment(
            db=db,
            request=request,
            project_id=org_entity.project_id,
            entity_type="organization",
            entity_id=org_entity.id,
            include_provenance=include_provenance,
            include_aliases=include_aliases,
            include_candidate_counts=include_candidate_counts,
            include_timeline=include_timeline,
            include_policy_status=include_policy_status,
        ))
    return data


def _parse_json_field(value):
    parsed = safe_json_loads(value)
    return parsed if parsed is not None else value


async def _export_character_payload(character: Character) -> dict:
    return {
        "name": character.name,
        "age": character.age,
        "gender": character.gender,
        "is_organization": False,
        "role_type": character.role_type,
        "personality": character.personality,
        "background": character.background,
        "appearance": character.appearance,
        "traits": _parse_json_field(character.traits),
        "organization_type": None,
        "organization_purpose": None,
        "avatar_url": character.avatar_url,
        "main_career_id": character.main_career_id,
        "main_career_stage": character.main_career_stage,
        "sub_careers": character.sub_careers,
        "created_at": character.created_at.isoformat() if character.created_at else None,
    }


async def _export_organization_payload(org_entity: OrganizationEntity, db: AsyncSession) -> dict:
    bridge = await _ensure_organization_bridge(org_entity, db)
    org_data = {
        "name": org_entity.name,
        "age": None,
        "gender": None,
        "is_organization": True,
        "role_type": "organization",
        "personality": org_entity.personality,
        "background": org_entity.background,
        "appearance": None,
        "traits": _parse_json_field(org_entity.traits),
        "organization_type": org_entity.organization_type,
        "organization_purpose": org_entity.organization_purpose,
        "avatar_url": org_entity.avatar_url,
        "main_career_id": None,
        "main_career_stage": None,
        "sub_careers": None,
        "created_at": org_entity.created_at.isoformat() if org_entity.created_at else None,
        "power_level": org_entity.power_level,
        "location": org_entity.location,
        "motto": org_entity.motto,
        "color": org_entity.color,
        "organization_entity_id": org_entity.id,
        "organization_id": bridge.id,
    }
    members = (await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_entity_id == org_entity.id)
    )).scalars().all()
    if members:
        org_data["organization_members_data"] = [
            {
                "character_id": member.character_id,
                "position": member.position,
                "rank": member.rank,
                "loyalty": member.loyalty,
                "contribution": member.contribution,
                "status": member.status,
                "joined_at": member.joined_at,
                "source": member.source,
            }
            for member in members
        ]
    return org_data


@router.get("", response_model=CharacterListResponse, summary="获取角色列表")
async def get_characters(
    project_id: str,
    request: Request,
    include_provenance: bool = Query(False),
    include_aliases: bool = Query(False),
    include_candidate_counts: bool = Query(False),
    include_timeline: bool = Query(False),
    include_policy_status: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有角色（query参数版本）"""
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(project_id, user_id, db)
    
    # 获取角色列表
    result = await db.execute(
        select(Character)
        .where(Character.project_id == project_id)
        .order_by(Character.created_at.desc())
    )
    characters = result.scalars().all()
    org_result = await db.execute(
        select(OrganizationEntity)
        .where(OrganizationEntity.project_id == project_id)
        .order_by(OrganizationEntity.created_at.desc())
    )
    organizations = org_result.scalars().all()

    items = []
    for char in characters:
        items.append(await _character_response_dict(
            char,
            db,
            request,
            include_provenance=include_provenance,
            include_aliases=include_aliases,
            include_candidate_counts=include_candidate_counts,
            include_timeline=include_timeline,
            include_policy_status=include_policy_status,
        ))
    for org in organizations:
        items.append(await _organization_as_character_response_dict(
            org,
            db,
            request,
            include_provenance=include_provenance,
            include_aliases=include_aliases,
            include_candidate_counts=include_candidate_counts,
            include_timeline=include_timeline,
            include_policy_status=include_policy_status,
        ))

    items.sort(key=lambda item: item.get("created_at") or item.get("updated_at"), reverse=True)
    return CharacterListResponse(total=len(items), items=items)


@router.get("/project/{project_id}", response_model=CharacterListResponse, summary="获取项目的所有角色")
async def get_project_characters(
    project_id: str,
    request: Request,
    include_provenance: bool = Query(False),
    include_aliases: bool = Query(False),
    include_candidate_counts: bool = Query(False),
    include_timeline: bool = Query(False),
    include_policy_status: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """获取指定项目的所有角色（路径参数版本）"""
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(project_id, user_id, db)
    
    return await get_characters(
        project_id=project_id,
        request=request,
        include_provenance=include_provenance,
        include_aliases=include_aliases,
        include_candidate_counts=include_candidate_counts,
        include_timeline=include_timeline,
        include_policy_status=include_policy_status,
        db=db,
    )


@router.get("/{character_id}", response_model=CharacterResponse, summary="获取角色详情")
async def get_character(
    character_id: str,
    request: Request,
    include_provenance: bool = Query(False),
    include_aliases: bool = Query(False),
    include_candidate_counts: bool = Query(False),
    include_timeline: bool = Query(False),
    include_policy_status: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """根据ID获取角色详情"""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()
    
    if not character:
        org_entity = await _get_organization_entity(character_id, db)
        if not org_entity:
            raise HTTPException(status_code=404, detail="角色不存在")
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(org_entity.project_id, user_id, db)
        return await _organization_as_character_response_dict(
            org_entity,
            db,
            request,
            include_provenance=include_provenance,
            include_aliases=include_aliases,
            include_candidate_counts=include_candidate_counts,
            include_timeline=include_timeline,
            include_policy_status=include_policy_status,
        )
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    return await _character_response_dict(
        character,
        db,
        request,
        include_provenance=include_provenance,
        include_aliases=include_aliases,
        include_candidate_counts=include_candidate_counts,
        include_timeline=include_timeline,
        include_policy_status=include_policy_status,
    )


@router.put("/{character_id}", response_model=CharacterResponse, summary="更新角色")
async def update_character(
    character_id: str,
    character_update: CharacterUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """更新角色信息"""
    from app.models.career import CharacterCareer, Career
    
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()
    
    if not character:
        org_entity = await _get_organization_entity(character_id, db)
        if not org_entity:
            raise HTTPException(status_code=404, detail="角色不存在")
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(org_entity.project_id, user_id, db)
        update_data = character_update.model_dump(exclude_unset=True)
        org_field_map = {
            "name": "name",
            "personality": "personality",
            "background": "background",
            "traits": "traits",
            "organization_type": "organization_type",
            "organization_purpose": "organization_purpose",
            "power_level": "power_level",
            "location": "location",
            "motto": "motto",
            "color": "color",
        }
        for source_field, target_field in org_field_map.items():
            if source_field in update_data:
                setattr(org_entity, target_field, update_data[source_field])
        if "name" in update_data:
            org_entity.normalized_name = normalized_name(update_data["name"])
        await db.commit()
        await db.refresh(org_entity)
        return await _organization_as_character_response_dict(org_entity, db)
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    # 更新字段
    update_data = character_update.model_dump(exclude_unset=True)
    
    for org_only_field in (
        'power_level', 'location', 'motto', 'color', 'organization_type',
        'organization_purpose', 'organization_members', 'is_organization'
    ):
        update_data.pop(org_only_field, None)
    
    # 处理主职业和副职业更新
    main_career_id = update_data.pop('main_career_id', None)
    main_career_stage = update_data.pop('main_career_stage', None)
    sub_careers_json = update_data.pop('sub_careers', None)
    
    if main_career_id is not None:
        # 验证职业存在
        if main_career_id:  # 不为空
            career_result = await db.execute(
                select(Career).where(
                    Career.id == main_career_id,
                    Career.project_id == character.project_id,
                    Career.type == 'main'
                )
            )
            career = career_result.scalar_one_or_none()
            
            if not career:
                raise HTTPException(status_code=400, detail="主职业不存在或类型错误")
            
            # 验证阶段有效性
            if main_career_stage and main_career_stage > career.max_stage:
                raise HTTPException(status_code=400, detail=f"阶段超出范围，该职业最大阶段为{career.max_stage}")
            
            # 更新或创建CharacterCareer关联
            char_career_result = await db.execute(
                select(CharacterCareer).where(
                    CharacterCareer.character_id == character_id,
                    CharacterCareer.career_type == 'main'
                )
            )
            char_career = char_career_result.scalar_one_or_none()
            
            if char_career:
                # 更新现有关联
                char_career.career_id = main_career_id
                if main_career_stage:
                    char_career.current_stage = main_career_stage
                logger.info(f"更新主职业关联：{character.name} -> {career.name}")
            else:
                # 创建新关联
                char_career = CharacterCareer(
                    character_id=character_id,
                    career_id=main_career_id,
                    career_type='main',
                    current_stage=main_career_stage or 1,
                    stage_progress=0
                )
                db.add(char_career)
                logger.info(f"创建主职业关联：{character.name} -> {career.name}")
            
            # 更新Character表的冗余字段
            character.main_career_id = main_career_id
            character.main_career_stage = main_career_stage or char_career.current_stage
        else:
            # 清空主职业
            char_career_result = await db.execute(
                select(CharacterCareer).where(
                    CharacterCareer.character_id == character_id,
                    CharacterCareer.career_type == 'main'
                )
            )
            char_career = char_career_result.scalar_one_or_none()
            if char_career:
                await db.delete(char_career)
                logger.info(f"移除主职业关联：{character.name}")
            
            character.main_career_id = None
            character.main_career_stage = None
    elif main_career_stage is not None and character.main_career_id:
        # 只更新阶段
        char_career_result = await db.execute(
            select(CharacterCareer).where(
                CharacterCareer.character_id == character_id,
                CharacterCareer.career_type == 'main'
            )
        )
        char_career = char_career_result.scalar_one_or_none()
        if char_career:
            char_career.current_stage = main_career_stage
            character.main_career_stage = main_career_stage
            logger.info(f"更新主职业阶段：{character.name} -> 阶段{main_career_stage}")
    
    # 处理副职业更新
    if sub_careers_json is not None:
        # 解析副职业JSON
        try:
            sub_careers_data = json.loads(sub_careers_json) if isinstance(sub_careers_json, str) else sub_careers_json
        except Exception:
            sub_careers_data = []
        
        # 删除现有的所有副职业关联
        existing_subs = await db.execute(
            select(CharacterCareer).where(
                CharacterCareer.character_id == character_id,
                CharacterCareer.career_type == 'sub'
            )
        )
        for sub_career in existing_subs.scalars():
            await db.delete(sub_career)
        
        # 创建新的副职业关联
        for sub_data in sub_careers_data[:2]:  # 最多2个副职业
            career_id = sub_data.get('career_id')
            if not career_id:
                continue
                
            # 验证副职业存在
            career_result = await db.execute(
                select(Career).where(
                    Career.id == career_id,
                    Career.project_id == character.project_id,
                    Career.type == 'sub'
                )
            )
            career = career_result.scalar_one_or_none()
            
            if career:
                # 创建副职业关联
                char_career = CharacterCareer(
                    character_id=character_id,
                    career_id=career_id,
                    career_type='sub',
                    current_stage=sub_data.get('stage', 1),
                    stage_progress=0
                )
                db.add(char_career)
                logger.info(f"添加副职业关联：{character.name} -> {career.name}")
        
        # 更新Character表的sub_careers冗余字段
        character.sub_careers = sub_careers_json if isinstance(sub_careers_json, str) else json.dumps(sub_careers_data, ensure_ascii=False)
        logger.info(f"更新副职业信息：{character.name}")
    
    # 更新 Character 表字段（排除 relationships 和 organization_members，这些字段现在由结构化表驱动）
    update_data.pop('relationships', None)
    update_data.pop('organization_members', None)
    for field, value in update_data.items():
        setattr(character, field, value)
    
    await db.commit()
    await db.refresh(character)
    
    logger.info(f"更新角色/组织成功：{character.name} (ID: {character_id})")
    
    return await _character_response_dict(character, db)


@router.delete("/{character_id}", summary="删除角色")
async def delete_character(
    character_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """删除角色"""
    from app.models.career import CharacterCareer
    
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()
    
    if not character:
        org_entity = await _get_organization_entity(character_id, db)
        if not org_entity:
            raise HTTPException(status_code=404, detail="角色不存在")
        user_id = getattr(request.state, 'user_id', None)
        await verify_project_access(org_entity.project_id, user_id, db)
        members = (await db.execute(
            select(OrganizationMember).where(OrganizationMember.organization_entity_id == org_entity.id)
        )).scalars().all()
        for member in members:
            await db.delete(member)
        bridges = (await db.execute(
            select(Organization).where(Organization.organization_entity_id == org_entity.id)
        )).scalars().all()
        for bridge in bridges:
            await db.delete(bridge)
        await db.delete(org_entity)
        await db.commit()
        logger.info(f"删除组织成功：{org_entity.name} (ID: {character_id})")
        return {"message": "角色删除成功"}
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character.project_id, user_id, db)
    
    # 清理角色-职业关联关系
    career_relations_result = await db.execute(
        select(CharacterCareer).where(CharacterCareer.character_id == character_id)
    )
    career_relations = career_relations_result.scalars().all()
    
    for relation in career_relations:
        await db.delete(relation)
        logger.info(f"删除角色职业关联：character_id={character_id}, career_id={relation.career_id}, type={relation.career_type}")
    
    # 删除角色
    await db.delete(character)
    await db.commit()
    
    logger.info(f"删除角色成功：{character.name} (ID: {character_id}), 清理了 {len(career_relations)} 条职业关联")
    
    return {"message": "角色删除成功"}


@router.post("", response_model=CharacterResponse, summary="手动创建角色")
async def create_character(
    character_data: CharacterCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    手动创建角色或组织
    
    - 可以创建普通角色（is_organization=False）
    - 也可以创建组织（is_organization=True）
    - 如果创建组织且提供了组织额外字段，会自动创建Organization详情记录
    - 支持设置主职业和副职业
    """
    from app.models.career import CharacterCareer, Career
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(character_data.project_id, user_id, db)
    
    try:
        request_data = character_data.model_dump()
        if request_data.get("is_organization", False):
            org_entity = OrganizationEntity(
                project_id=character_data.project_id,
                name=character_data.name,
                normalized_name=normalized_name(character_data.name),
                personality=character_data.personality,
                background=character_data.background,
                traits=request_data.get("traits"),
                avatar_url=request_data.get("avatar_url"),
                organization_type=request_data.get("organization_type"),
                organization_purpose=request_data.get("organization_purpose"),
                power_level=request_data.get("power_level") or 50,
                location=request_data.get("location"),
                motto=request_data.get("motto"),
                color=request_data.get("color"),
                source="manual",
            )
            db.add(org_entity)
            await db.flush()
            await _ensure_organization_bridge(org_entity, db)
            await db.commit()
            await db.refresh(org_entity)
            logger.info(f"✅ 手动创建组织成功：{org_entity.name} (ID: {org_entity.id})")
            return await _organization_as_character_response_dict(org_entity, db)

        # 创建角色（不再写入 relationships 文本字段，关系统一由 character_relationships 表管理）
        character = Character(
            project_id=character_data.project_id,
            name=character_data.name,
            age=character_data.age,
            gender=character_data.gender,
            role_type=character_data.role_type or "supporting",
            personality=character_data.personality,
            background=character_data.background,
            appearance=character_data.appearance,
            traits=character_data.traits,
            avatar_url=character_data.avatar_url,
            main_career_id=character_data.main_career_id,
            main_career_stage=character_data.main_career_stage,
            sub_careers=character_data.sub_careers
        )
        db.add(character)
        await db.flush()  # 获取character.id
        
        logger.info(f"✅ 手动创建角色成功：{character.name} (ID: {character.id})")
        
        # 处理主职业关联
        if character_data.main_career_id:
            # 验证职业存在
            career_result = await db.execute(
                select(Career).where(
                    Career.id == character_data.main_career_id,
                    Career.project_id == character_data.project_id,
                    Career.type == 'main'
                )
            )
            career = career_result.scalar_one_or_none()
            
            if career:
                # 创建主职业关联
                char_career = CharacterCareer(
                    character_id=character.id,
                    career_id=character_data.main_career_id,
                    career_type='main',
                    current_stage=character_data.main_career_stage or 1,
                    stage_progress=0
                )
                db.add(char_career)
                logger.info(f"✅ 创建主职业关联：{character.name} -> {career.name}")
            else:
                logger.warning(f"⚠️ 主职业ID不存在或类型错误: {character_data.main_career_id}")
        
        # 处理副职业关联
        if character_data.sub_careers:
            try:
                sub_careers_data = json.loads(character_data.sub_careers) if isinstance(character_data.sub_careers, str) else character_data.sub_careers
                
                for sub_data in sub_careers_data[:2]:  # 最多2个副职业
                    career_id = sub_data.get('career_id')
                    if not career_id:
                        continue
                    
                    # 验证副职业存在
                    career_result = await db.execute(
                        select(Career).where(
                            Career.id == career_id,
                            Career.project_id == character_data.project_id,
                            Career.type == 'sub'
                        )
                    )
                    career = career_result.scalar_one_or_none()
                    
                    if career:
                        # 创建副职业关联
                        char_career = CharacterCareer(
                            character_id=character.id,
                            career_id=career_id,
                            career_type='sub',
                            current_stage=sub_data.get('stage', 1),
                            stage_progress=0
                        )
                        db.add(char_career)
                        logger.info(f"✅ 创建副职业关联：{character.name} -> {career.name}")
                    else:
                        logger.warning(f"⚠️ 副职业ID不存在或类型错误: {career_id}")
            except Exception as e:
                logger.warning(f"⚠️ 解析副职业数据失败: {e}")
        
        await db.commit()
        await db.refresh(character)
        
        logger.info(f"🎉 成功手动创建角色/组织: {character.name}")
        
        return await _character_response_dict(character, db)
        
    except Exception as e:
        logger.error(f"手动创建角色失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建角色失败: {str(e)}")


@router.post("/generate-stream", summary="AI生成角色（流式）")
async def generate_character_stream(
    request: CharacterGenerateRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    user_ai_service: AIService = Depends(get_user_ai_service)
):
    """
    使用AI生成角色卡（支持SSE流式进度显示）
    
    通过Server-Sent Events返回实时进度信息
    """
    async def generate() -> AsyncGenerator[str, None]:
        tracker = WizardProgressTracker("角色")
        try:
            # 验证用户权限和项目是否存在
            user_id = getattr(http_request.state, 'user_id', None)
            project = await verify_project_access(request.project_id, user_id, db)
            policy_decision = await entity_generation_policy_service.evaluate_for_user(
                db,
                actor_user_id=user_id,
                project_id=request.project_id,
                entity_type="character",
                source_endpoint="api.characters.generate_character_stream",
                action_type="ai_generation",
                is_admin=bool(getattr(http_request.state, "is_admin", False)),
                provider=getattr(user_ai_service, "api_provider", None),
                model=getattr(user_ai_service, "default_model", None),
                reason="AI角色生成流式接口创建规范角色",
            )
            if not policy_decision.allowed:
                yield await tracker.error(policy_decision.message, 403)
                yield await tracker.result(candidate_policy_payload(policy_decision.to_response()))
                yield await tracker.done()
                return
            
            yield await tracker.start()
            
            # 获取已存在的角色列表
            yield await tracker.loading("获取项目上下文...", 0.3)
            
            existing_chars_result = await db.execute(
                select(Character)
                .where(Character.project_id == request.project_id)
                .order_by(Character.created_at.desc())
            )
            existing_characters = existing_chars_result.scalars().all()
            
            # 构建现有角色信息摘要
            existing_chars_info = ""
            character_list = []
            organization_list = []
            
            if existing_characters:
                for c in existing_characters[:10]:
                    character_list.append(f"- {c.name}（{c.role_type or '未知'}）")

                existing_orgs_result = await db.execute(
                    select(OrganizationEntity)
                    .where(OrganizationEntity.project_id == request.project_id)
                    .order_by(OrganizationEntity.created_at.desc())
                    .limit(10)
                )
                for org in existing_orgs_result.scalars().all():
                    organization_list.append(f"- {org.name} [{org.organization_type or '组织'}]")
                
                if character_list:
                    existing_chars_info += "\n已有角色：\n" + "\n".join(character_list)
                if organization_list:
                    existing_chars_info += "\n\n已有组织：\n" + "\n".join(organization_list)
            
            # 🎯 获取项目职业列表
            from app.models.career import Career
            careers_result = await db.execute(
                select(Career)
                .where(Career.project_id == request.project_id)
                .order_by(Career.type, Career.name)
            )
            careers = careers_result.scalars().all()
            
            # 构建职业信息摘要
            careers_info = ""
            if careers:
                main_careers = [c for c in careers if c.type == 'main']
                sub_careers = [c for c in careers if c.type == 'sub']
                
                if main_careers:
                    careers_info += "\n\n可用主职业列表（请在career_info中填写职业名称，系统会自动匹配ID）：\n"
                    for career in main_careers:
                        # 解析阶段信息
                        import json as json_lib
                        try:
                            stages = json_lib.loads(career.stages) if career.stages else []
                            stage_names = [s.get('name', f'阶段{s.get("level")}') for s in stages[:3]]  # 只显示前3个阶段
                            stage_info = " → ".join(stage_names)
                            if len(stages) > 3:
                                stage_info += " → ..."
                        except Exception:
                            stage_info = f"共{career.max_stage}个阶段"
                        
                        careers_info += f"- 名称: {career.name}"
                        if career.description:
                            careers_info += f", 描述: {career.description[:50]}"
                        careers_info += f", 阶段: {stage_info}\n"
                
                if sub_careers:
                    careers_info += "\n可用副职业列表（请在career_info中填写职业名称，系统会自动匹配ID）：\n"
                    for career in sub_careers[:5]:  # 最多显示5个副职业
                        careers_info += f"- 名称: {career.name}"
                        if career.description:
                            careers_info += f", 描述: {career.description[:50]}"
                        careers_info += "\n"
            else:
                careers_info = "\n\n⚠️ 项目中暂无职业设定"
            
            # 构建项目上下文
            project_context = f"""
项目信息：
- 书名：{project.title}
- 主题：{project.theme or '未设定'}
- 类型：{project.genre or '未设定'}
- 时间背景：{project.world_time_period or '未设定'}
- 地理位置：{project.world_location or '未设定'}
- 氛围基调：{project.world_atmosphere or '未设定'}
- 世界规则：{project.world_rules or '未设定'}
{existing_chars_info}
{careers_info}
"""
            
            user_input = f"""
用户要求：
- 角色名称：{request.name or '请AI生成'}
- 角色定位：{request.role_type or 'supporting'}
- 背景设定：{request.background or '无特殊要求'}
- 其他要求：{request.requirements or '无'}
"""
            
            yield await tracker.loading("项目上下文准备完成", 0.7)
            yield await tracker.preparing("构建AI提示词...")
            
            # 获取自定义提示词模板
            template = await PromptService.get_template("SINGLE_CHARACTER_GENERATION", user_id, db)
            # 格式化提示词
            prompt = PromptService.format_prompt(
                template,
                project_context=project_context,
                user_input=user_input
            )
            
            yield await tracker.generating(0, max(3000, len(prompt) * 8), "调用AI服务生成角色...")
            logger.info(f"🎯 开始为项目 {request.project_id} 生成角色（SSE流式）")
            
            try:
                # 直接使用 AIService 流式生成
                ai_response = ""
                chunk_count = 0
                estimated_total = max(3000, len(prompt) * 8)
                
                logger.info(f"🎯 开始生成角色（流式模式）...")
                yield await tracker.generating(0, estimated_total, "开始生成角色...")
                
                async for chunk in user_ai_service.generate_text_stream(
                    prompt=prompt,
                    tool_choice="required",
                ):
                    # chunk 现在可能是 dict 或 str，提取 content 字段
                    if isinstance(chunk, dict):
                        content = chunk.get("content", "")
                    else:
                        content = chunk
                    
                    if content:
                        ai_response += content
                        
                        # 发送内容块
                        yield await SSEResponse.send_chunk(content)
                        
                        # 定期更新进度（每收到约500字符更新一次，避免过于频繁）
                        current_len = len(ai_response)
                        if current_len >= chunk_count * 500:
                            chunk_count += 1
                            yield await tracker.generating(current_len, estimated_total)
                        
                        # 心跳
                        if chunk_count % 20 == 0:
                            yield await tracker.heartbeat()
                        
            except Exception as ai_error:
                logger.error(f"❌ AI服务调用异常：{str(ai_error)}")
                yield await tracker.error(f"AI服务调用失败：{str(ai_error)}")
                return
            
            if not ai_response or not ai_response.strip():
                yield await tracker.error("AI服务返回空响应")
                return
            
            yield await tracker.parsing("解析AI响应...", 0.5)
            
            # ✅ 使用统一的 JSON 清洗方法
            try:
                cleaned_response = user_ai_service._clean_json_response(ai_response)
                character_data = json.loads(cleaned_response)
                logger.info(f"✅ 角色JSON解析成功")
            except json.JSONDecodeError as e:
                logger.error(f"❌ 角色JSON解析失败: {e}")
                logger.error(f"   原始响应预览: {ai_response[:200]}")
                yield await tracker.error(f"AI返回的内容无法解析为JSON：{str(e)}")
                return
            
            yield await tracker.saving("创建角色记录...", 0.3)
            
            # 转换traits
            traits_json = json.dumps(character_data.get("traits", []), ensure_ascii=False) if character_data.get("traits") else None
            is_organization = character_data.get("is_organization", False)
            
            # 提取职业信息（支持通过名称匹配）
            career_info = character_data.get("career_info", {})
            raw_main_career_name = career_info.get("main_career_name") if career_info else None
            main_career_stage = career_info.get("main_career_stage", 1) if career_info else None
            raw_sub_careers_data = career_info.get("sub_careers", []) if career_info else []
            
            # 调试日志：输出职业信息
            logger.info(f"🔍 提取职业信息 - career_info: {career_info}")
            logger.info(f"🔍 raw_main_career_name: {raw_main_career_name}, main_career_stage: {main_career_stage}")
            logger.info(f"🔍 raw_sub_careers_data类型: {type(raw_sub_careers_data)}, 内容: {raw_sub_careers_data}")
            
            # 🔧 通过职业名称匹配数据库中的职业ID
            from app.models.career import Career
            main_career_id = None
            sub_careers_data = []
            
            # 匹配主职业名称
            if raw_main_career_name and not is_organization:
                career_check = await db.execute(
                    select(Career).where(
                        Career.name == raw_main_career_name,
                        Career.project_id == request.project_id,
                        Career.type == 'main'
                    )
                )
                matched_career = career_check.scalar_one_or_none()
                if matched_career:
                    main_career_id = matched_career.id
                    logger.info(f"✅ 主职业名称匹配成功: {raw_main_career_name} -> ID: {main_career_id}")
                else:
                    logger.warning(f"⚠️ AI返回的主职业名称未找到: {raw_main_career_name}")
            
            # 匹配副职业名称
            if raw_sub_careers_data and not is_organization and isinstance(raw_sub_careers_data, list):
                for sub_data in raw_sub_careers_data[:2]:
                    if isinstance(sub_data, dict):
                        career_name = sub_data.get('career_name')
                        if career_name:
                            career_check = await db.execute(
                                select(Career).where(
                                    Career.name == career_name,
                                    Career.project_id == request.project_id,
                                    Career.type == 'sub'
                                )
                            )
                            matched_career = career_check.scalar_one_or_none()
                            if matched_career:
                                # 转换为包含ID的格式
                                sub_careers_data.append({
                                    'career_id': matched_career.id,
                                    'stage': sub_data.get('stage', 1)
                                })
                                logger.info(f"✅ 副职业名称匹配成功: {career_name} -> ID: {matched_career.id}")
                            else:
                                logger.warning(f"⚠️ AI返回的副职业名称未找到: {career_name}")

            if is_organization:
                org_entity = OrganizationEntity(
                    project_id=request.project_id,
                    name=character_data.get("name", request.name or "未命名组织"),
                    normalized_name=normalized_name(character_data.get("name", request.name or "未命名组织")),
                    personality=character_data.get("personality", ""),
                    background=character_data.get("background", ""),
                    organization_type=character_data.get("organization_type"),
                    organization_purpose=character_data.get("organization_purpose"),
                    traits=traits_json,
                    power_level=character_data.get("power_level", 50),
                    location=character_data.get("location"),
                    motto=character_data.get("motto"),
                    color=character_data.get("color"),
                    source="ai",
                )
                db.add(org_entity)
                await db.flush()
                await _ensure_organization_bridge(org_entity, db)

                history = GenerationHistory(
                    project_id=request.project_id,
                    prompt=prompt,
                    generated_content=ai_response,
                    model=user_ai_service.default_model
                )
                db.add(history)
                entity_generation_policy_service.record_override_audit(
                    db,
                    policy_decision,
                    [org_entity.id],
                    extra_payload={"history_model": user_ai_service.default_model},
                )
                await db.commit()
                await db.refresh(org_entity)
                yield await tracker.complete("组织生成完成！")
                yield await tracker.result({
                    "character": {
                        "id": org_entity.id,
                        "name": org_entity.name,
                        "role_type": "organization",
                        "is_organization": True
                    }
                })
                yield await tracker.done()
                return
            
            # 创建角色（不再写入 relationships 文本字段，关系统一由 character_relationships 表管理）
            character = Character(
                project_id=request.project_id,
                name=character_data.get("name", request.name or "未命名角色"),
                age=str(character_data.get("age", "")),
                gender=character_data.get("gender"),
                role_type=request.role_type or "supporting",
                personality=character_data.get("personality", ""),
                background=character_data.get("background", ""),
                appearance=character_data.get("appearance", ""),
                traits=traits_json,
                main_career_id=main_career_id,
                main_career_stage=main_career_stage if main_career_id else None,
                sub_careers=json.dumps(sub_careers_data, ensure_ascii=False) if sub_careers_data else None
            )
            db.add(character)
            await db.flush()
            
            logger.info(f"✅ 角色创建成功：{character.name} (ID: {character.id})")
            
            # 处理主职业关联
            if main_career_id and not is_organization:
                from app.models.career import CharacterCareer, Career
                
                career_result = await db.execute(
                    select(Career).where(
                        Career.id == main_career_id,
                        Career.project_id == request.project_id,
                        Career.type == 'main'
                    )
                )
                career = career_result.scalar_one_or_none()
                
                if career:
                    char_career = CharacterCareer(
                        character_id=character.id,
                        career_id=main_career_id,
                        career_type='main',
                        current_stage=main_career_stage,
                        stage_progress=0
                    )
                    db.add(char_career)
                    logger.info(f"✅ AI生成角色-创建主职业关联：{character.name} -> {career.name}")
                else:
                    logger.warning(f"⚠️ AI返回的主职业ID不存在: {main_career_id}")
            
            # 处理副职业关联
            if sub_careers_data and not is_organization:
                from app.models.career import CharacterCareer, Career
                
                logger.info(f"🔍 开始处理副职业关联，数据: {sub_careers_data}")
                
                # 确保sub_careers_data是列表
                if not isinstance(sub_careers_data, list):
                    logger.warning(f"⚠️ sub_careers_data不是列表类型: {type(sub_careers_data)}")
                    sub_careers_data = []
                
                for idx, sub_data in enumerate(sub_careers_data[:2]):  # 最多2个副职业
                    logger.info(f"🔍 处理第{idx+1}个副职业，数据: {sub_data}, 类型: {type(sub_data)}")
                    
                    # 兼容不同的数据格式
                    if isinstance(sub_data, dict):
                        career_id = sub_data.get('career_id')
                        stage = sub_data.get('stage', 1)
                    else:
                        logger.warning(f"⚠️ 副职业数据格式错误，应为dict: {sub_data}")
                        continue
                    
                    if not career_id:
                        logger.warning(f"⚠️ 副职业数据缺少career_id字段")
                        continue
                    
                    logger.info(f"🔍 查询副职业: career_id={career_id}, project_id={request.project_id}")
                    
                    career_result = await db.execute(
                        select(Career).where(
                            Career.id == career_id,
                            Career.project_id == request.project_id,
                            Career.type == 'sub'
                        )
                    )
                    career = career_result.scalar_one_or_none()
                    
                    if career:
                        char_career = CharacterCareer(
                            character_id=character.id,
                            career_id=career_id,
                            career_type='sub',
                            current_stage=stage,
                            stage_progress=0
                        )
                        db.add(char_career)
                        logger.info(f"✅ AI生成角色-创建副职业关联：{character.name} -> {career.name} (阶段{stage})")
                    else:
                        logger.warning(f"⚠️ AI返回的副职业ID不存在: {career_id} (项目ID: {request.project_id})")
            
            # 处理结构化关系数据（仅针对非组织角色）
            relationships_data = character_data.get("relationships", [])
            if relationships_data and isinstance(relationships_data, list):
                    logger.info(f"📊 开始处理 {len(relationships_data)} 条关系数据")
                    created_rels = 0
                    
                    for rel in relationships_data:
                        try:
                            target_name = rel.get("target_character_name")
                            if not target_name:
                                logger.debug(f"  ⚠️  关系缺少target_character_name，跳过")
                                continue
                            
                            target_result = await db.execute(
                                select(Character).where(
                                    Character.project_id == request.project_id,
                                    Character.name == target_name
                                )
                            )
                            target_char = target_result.scalar_one_or_none()
                            
                            if target_char:
                                # 检查是否已存在相同关系
                                merge_service = RelationshipMergeService(db)
                                existing_rel = await merge_service._find_existing_character_relationship(request.project_id, character.id, target_char.id)
                                if existing_rel is not None:
                                    logger.debug(f"  ℹ️  关系已存在：{character.name} -> {target_name}")
                                    continue

                                # 匹配预定义关系类型
                                relationship_type_id = None
                                rel_type_result = await db.execute(
                                    select(RelationshipType).where(
                                        RelationshipType.name == rel.get("relationship_type")
                                    )
                                )
                                rel_type = rel_type_result.scalar_one_or_none()
                                if rel_type:
                                    relationship_type_id = rel_type.id

                                merge_result = await merge_service.merge_character_relationship(
                                    project_id=request.project_id,
                                    character_from_id=character.id,
                                    character_to_id=target_char.id,
                                    relationship_type_id=relationship_type_id,
                                    relationship_name=rel.get("relationship_type", "未知关系"),
                                    intimacy_level=rel.get("intimacy_level", 50),
                                    description=rel.get("description", ""),
                                    started_at=rel.get("started_at"),
                                    source="ai",
                                    confidence=1.0,
                                    allow_conflict_apply=True,
                                )
                                if merge_result.relationship is not None:
                                    created_rels += 1
                                    logger.info(f"  ✅ 创建关系：{character.name} -> {target_name} ({rel.get('relationship_type')})")
                            else:
                                logger.warning(f"  ⚠️  目标角色不存在：{target_name}")
                                
                        except Exception as rel_error:
                            logger.warning(f"  ❌ 创建关系失败：{str(rel_error)}")
                            continue
                    
                    logger.info(f"✅ 成功创建 {created_rels} 条关系记录")
            
            # 处理组织成员关系（仅针对非组织角色）
            org_memberships = character_data.get("organization_memberships", [])
            if org_memberships and isinstance(org_memberships, list):
                    logger.info(f"🏢 开始处理 {len(org_memberships)} 条组织成员关系")
                    created_members = 0
                    
                    for membership in org_memberships:
                        try:
                            org_name = membership.get("organization_name")
                            if not org_name:
                                logger.debug(f"  ⚠️  组织成员关系缺少organization_name，跳过")
                                continue
                            
                            org_entity_result = await db.execute(
                                select(OrganizationEntity).where(
                                    OrganizationEntity.project_id == request.project_id,
                                    OrganizationEntity.name == org_name,
                                )
                            )
                            org_entity = org_entity_result.scalar_one_or_none()
                            
                            if org_entity:
                                org = await _ensure_organization_bridge(org_entity, db)
                                
                                # 检查是否已存在成员关系
                                existing_member = await db.execute(
                                    select(OrganizationMember).where(
                                        OrganizationMember.organization_id == org.id,
                                        OrganizationMember.organization_entity_id == org_entity.id,
                                        OrganizationMember.character_id == character.id
                                    )
                                )
                                if existing_member.scalar_one_or_none():
                                    logger.debug(f"  ℹ️  成员关系已存在：{character.name} -> {org_name}")
                                    continue
                                
                                # 创建成员关系
                                member = OrganizationMember(
                                    organization_id=org.id,
                                    organization_entity_id=org_entity.id,
                                    character_id=character.id,
                                    position=membership.get("position", "成员"),
                                    rank=membership.get("rank", 0),
                                    loyalty=membership.get("loyalty", 50),
                                    joined_at=membership.get("joined_at"),
                                    status=membership.get("status", "active"),
                                    source="ai"
                                )
                                db.add(member)
                                
                                # 更新组织成员计数
                                org_entity.member_count = (org_entity.member_count or 0) + 1
                                
                                created_members += 1
                                logger.info(f"  ✅ 添加成员：{character.name} -> {org_name} ({membership.get('position')})")
                            else:
                                logger.warning(f"  ⚠️  组织不存在：{org_name}")
                                
                        except Exception as org_error:
                            logger.warning(f"  ❌ 添加组织成员失败：{str(org_error)}")
                            continue
                    
                    logger.info(f"✅ 成功创建 {created_members} 条组织成员记录")
            
            yield await tracker.saving("保存生成历史...", 0.9)
            
            # 记录生成历史
            history = GenerationHistory(
                project_id=request.project_id,
                prompt=prompt,
                generated_content=ai_response,
                model=user_ai_service.default_model
            )
            db.add(history)
            entity_generation_policy_service.record_override_audit(
                db,
                policy_decision,
                [character.id],
                extra_payload={"history_model": user_ai_service.default_model},
            )
             
            await db.commit()
            await db.refresh(character)
            
            logger.info(f"🎉 成功生成角色: {character.name}")
            
            yield await tracker.complete("角色生成完成！")
            
            # 发送结果数据
            yield await tracker.result({
                "character": {
                    "id": character.id,
                    "name": character.name,
                    "role_type": character.role_type,
                    "is_organization": False
                }
            })
            
            yield await tracker.done()
            
        except HTTPException as he:
            logger.error(f"HTTP异常: {he.detail}")
            yield await tracker.error(he.detail, he.status_code)
        except Exception as e:
            logger.error(f"生成角色失败: {str(e)}")
            yield await tracker.error(f"生成角色失败: {str(e)}")
    
    return create_sse_response(generate())


@router.post("/export", summary="批量导出角色/组织")
async def export_characters(
    export_request: CharactersExportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    批量导出角色/组织为JSON格式
    
    - 支持单个或多个角色/组织导出
    - 包含角色的所有信息（基础信息、职业、组织详情等）
    - 返回JSON文件供下载
    """
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    if not export_request.character_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个角色/组织")
    
    try:
        exported_items = []
        # 验证所有角色/组织的权限，并按请求顺序构建兼容导出载荷
        for char_id in export_request.character_ids:
            result = await db.execute(
                select(Character).where(Character.id == char_id)
            )
            character = result.scalar_one_or_none()
            if character:
                await verify_project_access(character.project_id, user_id, db)
                exported_items.append(await _export_character_payload(character))
                continue

            org_entity = await _get_organization_entity(char_id, db)
            if not org_entity:
                raise HTTPException(status_code=404, detail=f"角色不存在: {char_id}")

            await verify_project_access(org_entity.project_id, user_id, db)
            exported_items.append(await _export_organization_payload(org_entity, db))

        from datetime import datetime
        export_data = {
            "version": ImportExportService.CURRENT_VERSION,
            "export_time": datetime.utcnow().isoformat(),
            "export_type": "characters",
            "count": len(exported_items),
            "data": exported_items,
        }

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        count = len(export_request.character_ids)
        filename = f"characters_export_{count}_{timestamp}.json"
        
        logger.info(f"用户 {user_id} 导出了 {count} 个角色/组织")
        
        # 返回JSON文件
        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "application/json; charset=utf-8"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出角色/组织失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/import", response_model=CharactersImportResult, summary="导入角色/组织")
async def import_characters(
    project_id: str,
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    从JSON文件导入角色/组织
    
    - 支持导入之前导出的角色/组织JSON文件
    - 自动处理重复名称（跳过）
    - 验证职业ID的有效性
    - 自动创建组织详情记录
    """
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 验证项目权限
    await verify_project_access(project_id, user_id, db)
    
    # 验证文件类型
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="只支持JSON格式文件")
    
    try:
        # 读取文件内容
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        
        # 执行导入
        result = await ImportExportService.import_characters(
            data=data,
            project_id=project_id,
            user_id=user_id,
            db=db
        )
        
        logger.info(f"用户 {user_id} 导入角色/组织到项目 {project_id}: {result['message']}")
        
        return result
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON格式错误: {str(e)}")
    except Exception as e:
        logger.error(f"导入角色/组织失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.post("/validate-import", summary="验证导入文件")
async def validate_import(
    file: UploadFile = File(...),
    request: Request = None
):
    """
    验证角色/组织导入文件的格式和内容
    
    - 检查文件格式
    - 验证版本兼容性
    - 统计数据量
    - 返回验证结果和警告信息
    """
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 验证文件类型
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="只支持JSON格式文件")
    
    try:
        # 读取文件内容
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        
        # 验证数据
        validation_result = ImportExportService.validate_characters_import(data)
        
        logger.info(f"用户 {user_id} 验证导入文件: {file.filename}")
        
        return validation_result
        
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "version": "",
            "statistics": {"characters": 0, "organizations": 0},
            "errors": [f"JSON格式错误: {str(e)}"],
            "warnings": []
        }
    except Exception as e:
        logger.error(f"验证导入文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")
