"""Compatibility helpers for legacy organization surfaces backed by OrganizationEntity."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.relationship import Organization, OrganizationEntity, OrganizationMember


def normalized_name(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


async def ensure_organization_bridge(entity: OrganizationEntity, db: AsyncSession) -> Organization:
    """Ensure the legacy organizations bridge exists for a canonical org entity."""

    result = await db.execute(select(Organization).where(Organization.organization_entity_id == entity.id))
    bridge = result.scalar_one_or_none()
    if bridge:
        return bridge

    bridge = Organization(
        project_id=entity.project_id,
        character_id=entity.legacy_character_id,
        organization_entity_id=entity.id,
    )
    db.add(bridge)
    await db.flush()
    return bridge


async def create_organization_entity_from_payload(
    *,
    project_id: str,
    payload: dict[str, Any],
    db: AsyncSession,
    source: str,
    name: str | None = None,
) -> tuple[OrganizationEntity, Organization]:
    """Create a canonical OrganizationEntity plus legacy bridge from old character-shaped data."""

    org_name = name or str(payload.get("name") or "未命名组织")
    traits = payload.get("traits")
    if isinstance(traits, (list, dict)):
        traits = json.dumps(traits, ensure_ascii=False)

    entity = OrganizationEntity(
        project_id=project_id,
        name=org_name[:100],
        normalized_name=normalized_name(org_name),
        personality=payload.get("personality") or payload.get("description") or "",
        background=payload.get("background") or "",
        current_state=payload.get("current_state"),
        avatar_url=payload.get("avatar_url"),
        traits=traits,
        organization_type=payload.get("organization_type"),
        organization_purpose=payload.get("organization_purpose"),
        status=payload.get("status") or "active",
        parent_org_id=payload.get("parent_org_id"),
        level=payload.get("level") or 0,
        power_level=payload.get("power_level") or 50,
        member_count=payload.get("member_count") or 0,
        location=payload.get("location"),
        motto=payload.get("motto"),
        color=payload.get("color"),
        source=source,
    )
    db.add(entity)
    await db.flush()
    bridge = await ensure_organization_bridge(entity, db)
    return entity, bridge


async def add_organization_member(
    *,
    db: AsyncSession,
    bridge: Organization,
    entity: OrganizationEntity,
    character_id: str,
    position: str = "成员",
    rank: int = 0,
    loyalty: int = 50,
    contribution: int = 0,
    status: str = "active",
    joined_at: str | None = None,
    source: str = "manual",
    notes: str | None = None,
) -> OrganizationMember:
    member = OrganizationMember(
        organization_id=bridge.id,
        organization_entity_id=entity.id,
        character_id=character_id,
        position=position,
        rank=rank,
        loyalty=loyalty,
        contribution=contribution,
        status=status,
        joined_at=joined_at,
        source=source,
        notes=notes,
    )
    db.add(member)
    return member


def legacy_org_payload(entity: OrganizationEntity, bridge: Organization | None = None) -> dict[str, Any]:
    return {
        "name": entity.name,
        "age": None,
        "gender": None,
        "is_organization": True,
        "role_type": "organization",
        "personality": entity.personality,
        "background": entity.background,
        "appearance": None,
        "traits": entity.traits,
        "organization_type": entity.organization_type,
        "organization_purpose": entity.organization_purpose,
        "avatar_url": entity.avatar_url,
        "main_career_id": None,
        "main_career_stage": None,
        "sub_careers": None,
        "power_level": entity.power_level,
        "location": entity.location,
        "motto": entity.motto,
        "color": entity.color,
        "organization_entity_id": entity.id,
        "organization_id": bridge.id if bridge else None,
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
    }
