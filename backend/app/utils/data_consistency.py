"""数据一致性辅助函数"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Tuple, List
from app.models.character import Character
from app.models.relationship import Organization, OrganizationEntity, OrganizationMember, CharacterRelationship
from app.services.organization_compat import ensure_organization_bridge
from app.logger import get_logger

logger = get_logger(__name__)


async def ensure_organization_record(
    entity: OrganizationEntity,
    db: AsyncSession,
    power_level: int = 50,
    location: Optional[str] = None,
    motto: Optional[str] = None
) -> Optional[Organization]:
    """
    确保 canonical OrganizationEntity 拥有对应的 legacy Organization bridge 记录
    
    Args:
        entity: OrganizationEntity 对象
        db: 数据库会话
        power_level: 势力等级（默认50）
        location: 所在地
        motto: 宗旨/口号
        
    Returns:
        Organization bridge 对象
    """
    # 检查是否已存在
    result = await db.execute(
        select(Organization).where(Organization.organization_entity_id == entity.id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        entity.power_level = entity.power_level or power_level
        entity.location = entity.location or location
        entity.motto = entity.motto or motto
        org = await ensure_organization_bridge(entity, db)
        await db.refresh(org)
        logger.info(f"✅ 自动创建组织桥接记录：{entity.name} (Org ID: {org.id})")
    else:
        logger.debug(f"组织桥接记录已存在：{entity.name} (Org ID: {org.id})")
    
    return org


async def sync_organization_member_count(
    organization: OrganizationEntity,
    db: AsyncSession
) -> int:
    """
    同步组织的成员计数，从实际成员记录计算
    
    Args:
        organization: OrganizationEntity 对象
        db: 数据库会话
        
    Returns:
        实际成员数量
    """
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_entity_id == organization.id,
            OrganizationMember.status == "active"
        )
    )
    members = result.scalars().all()
    actual_count = len(members)
    
    if organization.member_count != actual_count:
        logger.warning(
            f"组织 {organization.id} 成员计数不一致：" 
            f"记录值={organization.member_count}, 实际值={actual_count}，已修正"
        )
        organization.member_count = actual_count
        await db.flush()
    
    return actual_count


async def fix_missing_organization_records(
    project_id: str,
    db: AsyncSession
) -> Tuple[int, int]:
    """
    修复项目中缺失的 Organization bridge 记录
    
    Args:
        project_id: 项目ID
        db: 数据库会话
        
    Returns:
        (修复数量, 检查总数)
    """
    # 查找所有 canonical 组织实体
    result = await db.execute(
        select(OrganizationEntity).where(OrganizationEntity.project_id == project_id)
    )
    org_entities = result.scalars().all()
    
    fixed_count = 0
    for entity in org_entities:
        org = await ensure_organization_record(entity, db)
        if org and org.id:  # 新创建的才计数
            # 检查是否是新创建的（通过查询历史）
            result = await db.execute(
                select(Organization).where(Organization.organization_entity_id == entity.id)
            )
            if result.scalar_one_or_none():
                fixed_count += 1
    
    await db.commit()
    
    logger.info(f"📊 修复统计 - 检查了 {len(org_entities)} 个组织，修复了 {fixed_count} 个缺失的Organization桥接记录")
    return fixed_count, len(org_entities)


async def fix_organization_member_counts(
    project_id: str,
    db: AsyncSession
) -> Tuple[int, int]:
    """
    修复项目中所有组织的成员计数
    
    Args:
        project_id: 项目ID
        db: 数据库会话
        
    Returns:
        (修复数量, 检查总数)
    """
    # 查找所有组织
    result = await db.execute(
        select(OrganizationEntity).where(OrganizationEntity.project_id == project_id)
    )
    organizations = result.scalars().all()
    
    fixed_count = 0
    for org in organizations:
        old_count = org.member_count
        actual_count = await sync_organization_member_count(org, db)
        if old_count != actual_count:
            fixed_count += 1
    
    await db.commit()
    
    logger.info(f"📊 修复统计 - 检查了 {len(organizations)} 个组织，修复了 {fixed_count} 个计数错误")
    return fixed_count, len(organizations)


async def validate_relationships(
    project_id: str,
    db: AsyncSession
) -> List[dict]:
    """
    验证项目中的关系数据完整性
    
    检查所有关系中的character_from_id和character_to_id是否都指向存在的角色
    
    Args:
        project_id: 项目ID
        db: 数据库会话
        
    Returns:
        问题列表，每个问题包含 {issue_type, relationship_id, details}
    """
    issues = []
    
    # 获取所有关系
    result = await db.execute(
        select(CharacterRelationship).where(CharacterRelationship.project_id == project_id)
    )
    relationships = result.scalars().all()
    
    for rel in relationships:
        # 检查from角色
        from_char = await db.execute(
            select(Character).where(Character.id == rel.character_from_id)
        )
        if not from_char.scalar_one_or_none():
            issues.append({
                "issue_type": "missing_from_character",
                "relationship_id": rel.id,
                "details": f"关系 {rel.id} 的源角色 {rel.character_from_id} 不存在"
            })
        
        # 检查to角色
        to_char = await db.execute(
            select(Character).where(Character.id == rel.character_to_id)
        )
        if not to_char.scalar_one_or_none():
            issues.append({
                "issue_type": "missing_to_character",
                "relationship_id": rel.id,
                "details": f"关系 {rel.id} 的目标角色 {rel.character_to_id} 不存在"
            })
    
    if issues:
        logger.warning(f"⚠️  发现 {len(issues)} 个关系数据问题")
        for issue in issues:
            logger.warning(f"  - {issue['details']}")
    else:
        logger.info(f"✅ 所有 {len(relationships)} 条关系数据完整")
    
    return issues


async def validate_organization_members(
    project_id: str,
    db: AsyncSession
) -> List[dict]:
    """
    验证项目中的组织成员数据完整性
    
    检查所有成员关系中的organization_id和character_id是否都有效
    
    Args:
        project_id: 项目ID
        db: 数据库会话
        
    Returns:
        问题列表
    """
    issues = []
    
    # 获取所有成员关系
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id.in_(
                select(Organization.id).where(Organization.project_id == project_id)
            )
        )
    )
    members = result.scalars().all()
    
    for member in members:
        # 检查组织
        org = await db.execute(
            select(Organization).where(Organization.id == member.organization_id)
        )
        if not org.scalar_one_or_none():
            issues.append({
                "issue_type": "missing_organization",
                "member_id": member.id,
                "details": f"成员 {member.id} 的组织 {member.organization_id} 不存在"
            })
        
        # 检查角色
        char = await db.execute(
            select(Character).where(Character.id == member.character_id)
        )
        if not char.scalar_one_or_none():
            issues.append({
                "issue_type": "missing_character",
                "member_id": member.id,
                "details": f"成员 {member.id} 的角色 {member.character_id} 不存在"
            })
    
    if issues:
        logger.warning(f"⚠️  发现 {len(issues)} 个组织成员数据问题")
        for issue in issues:
            logger.warning(f"  - {issue['details']}")
    else:
        logger.info(f"✅ 所有 {len(members)} 条组织成员数据完整")
    
    return issues


async def run_full_data_consistency_check(
    project_id: str,
    db: AsyncSession,
    auto_fix: bool = True
) -> dict:
    """
    对项目运行完整的数据一致性检查和修复
    
    Args:
        project_id: 项目ID
        db: 数据库会话
        auto_fix: 是否自动修复问题（默认True）
        
    Returns:
        检查报告字典
    """
    logger.info(f"🔍 开始数据一致性检查 - 项目 {project_id}")
    
    report = {
        "project_id": project_id,
        "checks": {}
    }
    
    # 1. 检查并修复缺失的Organization记录
    if auto_fix:
        fixed, total = await fix_missing_organization_records(project_id, db)
        report["checks"]["organization_records"] = {
            "checked": total,
            "fixed": fixed,
            "status": "ok" if fixed == 0 else "fixed"
        }
    
    # 2. 检查并修复成员计数
    if auto_fix:
        fixed, total = await fix_organization_member_counts(project_id, db)
        report["checks"]["member_counts"] = {
            "checked": total,
            "fixed": fixed,
            "status": "ok" if fixed == 0 else "fixed"
        }
    
    # 3. 验证关系数据
    rel_issues = await validate_relationships(project_id, db)
    report["checks"]["relationships"] = {
        "issues_found": len(rel_issues),
        "issues": rel_issues,
        "status": "ok" if len(rel_issues) == 0 else "warning"
    }
    
    # 4. 验证组织成员数据
    member_issues = await validate_organization_members(project_id, db)
    report["checks"]["organization_members"] = {
        "issues_found": len(member_issues),
        "issues": member_issues,
        "status": "ok" if len(member_issues) == 0 else "warning"
    }
    
    logger.info(f"✅ 数据一致性检查完成")
    return report
