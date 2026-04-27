"""关系管理API"""
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import Any, List, Optional

from app.database import get_db
from app.models.relationship import (
    RelationshipType,
    EntityRelationship,
    EntityProvenance,
    ExtractionCandidate,
    OrganizationEntity,
    OrganizationMember,
    RelationshipTimelineEvent,
)
from app.models.character import Character
from app.schemas.relationship import (
    RelationshipTypeResponse,
    CharacterRelationshipCreate,
    CharacterRelationshipUpdate,
    CharacterRelationshipResponse,
    RelationshipGraphData,
    RelationshipGraphNode,
    RelationshipGraphLink
)
from app.logger import get_logger
from app.api.common import verify_project_access
from app.services.relationship_merge_service import RelationshipMergeService

router = APIRouter(prefix="/relationships", tags=["关系管理"])
logger = get_logger(__name__)


def _relationship_base_payload(relationship: EntityRelationship) -> dict[str, Any]:
    """Build the legacy-compatible relationship payload plus optional evidence slots."""
    return {
        "id": relationship.id,
        "project_id": relationship.project_id,
        "character_from_id": relationship.from_entity_id,
        "character_to_id": relationship.to_entity_id,
        "relationship_type_id": relationship.relationship_type_id,
        "relationship_name": relationship.relationship_name,
        "intimacy_level": relationship.intimacy_level,
        "status": relationship.status,
        "description": relationship.description,
        "started_at": relationship.started_at,
        "ended_at": relationship.ended_at,
        "source": relationship.source or "legacy",
        "created_at": relationship.created_at,
        "updated_at": relationship.updated_at,
    }


def _provenance_payload(provenance: EntityProvenance) -> dict[str, Any]:
    return {
        "id": provenance.id,
        "source_type": provenance.source_type,
        "source_id": provenance.source_id,
        "run_id": provenance.run_id,
        "candidate_id": provenance.candidate_id,
        "chapter_id": provenance.chapter_id,
        "claim_type": provenance.claim_type,
        "claim_payload": provenance.claim_payload,
        "evidence_text": provenance.evidence_text,
        "source_start": provenance.source_start,
        "source_end": provenance.source_end,
        "confidence": provenance.confidence,
        "status": provenance.status,
        "created_by": provenance.created_by,
        "created_at": provenance.created_at,
    }


def _history_payload(event: RelationshipTimelineEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "event_status": event.event_status,
        "relationship_name": event.relationship_name,
        "source_chapter_id": event.source_chapter_id,
        "source_chapter_order": event.source_chapter_order,
        "valid_from_chapter_id": event.valid_from_chapter_id,
        "valid_from_chapter_order": event.valid_from_chapter_order,
        "valid_to_chapter_id": event.valid_to_chapter_id,
        "valid_to_chapter_order": event.valid_to_chapter_order,
        "story_time_label": event.story_time_label,
        "source_start_offset": event.source_start_offset,
        "source_end_offset": event.source_end_offset,
        "evidence_text": event.evidence_text,
        "confidence": event.confidence,
        "provenance_id": event.provenance_id,
        "supersedes_event_id": event.supersedes_event_id,
        "created_at": event.created_at,
    }


async def _load_relationship_enrichment(
    db: AsyncSession,
    relationships: List[EntityRelationship],
) -> dict[str, dict[str, Any]]:
    """Load provenance/history/pending metadata for relationship list and graph views."""
    relationship_ids = [relationship.id for relationship in relationships]
    if not relationship_ids:
        return {}

    provenance_result = await db.execute(
        select(EntityProvenance)
        .where(
            EntityProvenance.entity_type == "relationship",
            EntityProvenance.entity_id.in_(relationship_ids),
            EntityProvenance.status == "active",
        )
        .order_by(EntityProvenance.created_at.desc(), EntityProvenance.id.desc())
    )
    provenance_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for provenance in provenance_result.scalars().all():
        provenance_map[provenance.entity_id].append(_provenance_payload(provenance))

    history_result = await db.execute(
        select(RelationshipTimelineEvent)
        .where(
            RelationshipTimelineEvent.relationship_id.in_(relationship_ids),
            RelationshipTimelineEvent.event_type == "relationship",
        )
        .order_by(RelationshipTimelineEvent.created_at.desc(), RelationshipTimelineEvent.id.desc())
    )
    history_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in history_result.scalars().all():
        if event.relationship_id:
            history_map[event.relationship_id].append(_history_payload(event))

    pending_result = await db.execute(
        select(ExtractionCandidate.canonical_target_id, func.count(ExtractionCandidate.id))
        .where(
            ExtractionCandidate.candidate_type == "relationship",
            ExtractionCandidate.status == "pending",
            ExtractionCandidate.canonical_target_type == "relationship",
            ExtractionCandidate.canonical_target_id.in_(relationship_ids),
        )
        .group_by(ExtractionCandidate.canonical_target_id)
    )
    pending_counts = {str(target_id): int(count) for target_id, count in pending_result.all() if target_id}

    enrichment: dict[str, dict[str, Any]] = {}
    for relationship_id in relationship_ids:
        history = history_map.get(relationship_id, [])
        provenance = provenance_map.get(relationship_id, [])
        latest_history = history[0] if history else None
        latest_provenance = provenance[0] if provenance else None
        enrichment[relationship_id] = {
            "source_chapter_id": (latest_history or {}).get("source_chapter_id") or (latest_provenance or {}).get("chapter_id"),
            "source_chapter_order": (latest_history or {}).get("source_chapter_order"),
            "evidence_text": (latest_history or {}).get("evidence_text") or (latest_provenance or {}).get("evidence_text"),
            "confidence": (latest_history or {}).get("confidence") if latest_history and latest_history.get("confidence") is not None else (latest_provenance or {}).get("confidence"),
            "provenance": provenance,
            "history": history,
            "pending_candidate_count": pending_counts.get(relationship_id, 0),
        }
    return enrichment


@router.get("/types", response_model=List[RelationshipTypeResponse], summary="获取关系类型列表")
async def get_relationship_types(db: AsyncSession = Depends(get_db)):
    """获取所有预定义的关系类型"""
    result = await db.execute(select(RelationshipType).order_by(RelationshipType.category, RelationshipType.id))
    types = result.scalars().all()
    return types


@router.get("/project/{project_id}", response_model=List[CharacterRelationshipResponse], summary="获取项目的所有关系")
async def get_project_relationships(
    project_id: str,
    request: Request,
    character_id: Optional[str] = Query(None, description="筛选特定角色的关系"),
    db: AsyncSession = Depends(get_db)
):
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(project_id, user_id, db)
    
    """
    获取项目中的所有角色关系
    
    - 如果提供character_id，则只返回与该角色相关的关系（作为发起方或接收方）
    - 否则返回项目中的所有关系
    """
    query = select(EntityRelationship).where(
        EntityRelationship.project_id == project_id,
        EntityRelationship.from_entity_type == "character",
        EntityRelationship.to_entity_type == "character",
    )
    
    if character_id:
        query = query.where(
            or_(
                EntityRelationship.from_entity_id == character_id,
                EntityRelationship.to_entity_id == character_id
            )
        )
    
    query = query.order_by(EntityRelationship.created_at.desc())
    result = await db.execute(query)
    relationships = result.scalars().all()
    enrichment = await _load_relationship_enrichment(db, relationships)
    payload = []
    for relationship in relationships:
        item = _relationship_base_payload(relationship)
        item.update(enrichment.get(relationship.id, {}))
        payload.append(item)
    
    logger.info(f"获取项目 {project_id} 的关系列表，共 {len(relationships)} 条")
    return payload


@router.get("/graph/{project_id}", response_model=RelationshipGraphData, summary="获取关系图谱数据")
async def get_relationship_graph(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(project_id, user_id, db)
    
    """
    获取用于可视化的关系图谱数据
    
    返回格式：
    - nodes: 角色节点列表
    - links: 关系连线列表
    """
    # 获取所有角色（节点）
    chars_result = await db.execute(
        select(Character).where(Character.project_id == project_id)
    )
    characters = chars_result.scalars().all()
    
    nodes = [
        RelationshipGraphNode(
            id=c.id,
            name=c.name,
            type="character",
            role_type=c.role_type,
            avatar=c.avatar_url
        )
        for c in characters
    ]
    orgs_result = await db.execute(
        select(OrganizationEntity).where(OrganizationEntity.project_id == project_id)
    )
    organizations = orgs_result.scalars().all()
    nodes.extend(
        RelationshipGraphNode(
            id=org.id,
            name=org.name,
            type="organization",
            role_type="organization",
            avatar=org.avatar_url,
        )
        for org in organizations
    )
    
    # 获取所有角色关系（边）
    rels_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.project_id == project_id
        )
    )
    relationships = rels_result.scalars().all()
    enrichment = await _load_relationship_enrichment(db, relationships)

    links = [
        RelationshipGraphLink(
            id=r.id,
            source=r.from_entity_id,
            target=r.to_entity_id,
            relationship=r.relationship_name or "未知关系",
            intimacy=r.intimacy_level,
            status=r.status,
            source_chapter_id=enrichment.get(r.id, {}).get("source_chapter_id"),
            source_chapter_order=enrichment.get(r.id, {}).get("source_chapter_order"),
            evidence_text=enrichment.get(r.id, {}).get("evidence_text"),
            confidence=enrichment.get(r.id, {}).get("confidence"),
            pending_candidate_count=enrichment.get(r.id, {}).get("pending_candidate_count", 0),
        )
        for r in relationships
    ]

    # 获取组织成员关系（组织 -> 成员）并追加到图谱边
    # source 使用 canonical OrganizationEntity.id，确保与组织节点一致
    members_result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_entity_id.in_([org.id for org in organizations]))
    )
    org_members = members_result.scalars().all()

    member_links = [
        RelationshipGraphLink(
            id=f"org-member-{member.id}",
            source=member.organization_entity_id,
            target=member.character_id,
            relationship=f"组织成员·{member.position}",
            intimacy=member.loyalty,
            status=member.status
        )
        for member in org_members
    ]

    links.extend(member_links)

    logger.info(
        f"获取项目 {project_id} 的关系图谱：{len(nodes)} 个节点，"
        f"{len(relationships)} 条角色关系，{len(member_links)} 条组织成员关系"
    )
    return RelationshipGraphData(nodes=nodes, links=links)


@router.post("/", response_model=CharacterRelationshipResponse, summary="创建角色关系")
async def create_relationship(
    relationship: CharacterRelationshipCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    手动创建角色关系
    
    - 需要提供角色A和角色B的ID
    - 可以指定预定义的关系类型或自定义关系名称
    - 可以设置亲密度、状态等属性
    """
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(relationship.project_id, user_id, db)
    
    # 验证角色是否存在
    char_from = await db.execute(
        select(Character).where(Character.id == relationship.character_from_id)
    )
    char_to = await db.execute(
        select(Character).where(Character.id == relationship.character_to_id)
    )
    
    if not char_from.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"角色A（ID: {relationship.character_from_id}）不存在")
    if not char_to.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"角色B（ID: {relationship.character_to_id}）不存在")
    
    merge_result = await RelationshipMergeService(db).merge_character_relationship(
        project_id=relationship.project_id,
        character_from_id=relationship.character_from_id,
        character_to_id=relationship.character_to_id,
        relationship_type_id=relationship.relationship_type_id,
        relationship_name=relationship.relationship_name,
        intimacy_level=relationship.intimacy_level,
        status=relationship.status,
        description=relationship.description,
        started_at=relationship.started_at,
        ended_at=relationship.ended_at,
        source="manual",
        confidence=1.0,
        allow_conflict_apply=True,
    )
    db_relationship = merge_result.relationship
    if db_relationship is None:
        raise HTTPException(status_code=409, detail=merge_result.reason or "关系需要评审")
    await db.commit()
    await db.refresh(db_relationship)
    
    logger.info(f"创建关系成功：{relationship.character_from_id} -> {relationship.character_to_id}")
    return db_relationship


@router.put("/{relationship_id}", response_model=CharacterRelationshipResponse, summary="更新关系")
async def update_relationship(
    relationship_id: str,
    relationship: CharacterRelationshipUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """更新角色关系的属性（亲密度、状态等）"""
    result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.id == relationship_id
        )
    )
    db_rel = result.scalar_one_or_none()
    
    if not db_rel:
        raise HTTPException(status_code=404, detail="关系不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(db_rel.project_id, user_id, db)
    
    update_data = relationship.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_rel, field, value)
    
    await db.commit()
    await db.refresh(db_rel)
    
    logger.info(f"更新关系成功：{relationship_id}")
    return db_rel


@router.delete("/{relationship_id}", summary="删除关系")
async def delete_relationship(
    relationship_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """删除角色关系"""
    result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.id == relationship_id
        )
    )
    db_rel = result.scalar_one_or_none()
    
    if not db_rel:
        raise HTTPException(status_code=404, detail="关系不存在")
    
    # 验证用户权限
    user_id = getattr(request.state, 'user_id', None)
    await verify_project_access(db_rel.project_id, user_id, db)
    
    await db.delete(db_rel)
    await db.commit()
    
    logger.info(f"删除关系成功：{relationship_id}")
    return {"message": "关系删除成功", "id": relationship_id}
