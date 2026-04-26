"""extraction graph and organization split

Revision ID: b7c8d9e0f1a2
Revises: 9a1b2c3d4e5f
Create Date: 2026-04-26 12:00:00

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = '9a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _legacy_org_rows() -> list[sa.engine.RowMapping]:
    return op.get_bind().execute(sa.text(
        """
        SELECT
            c.id AS legacy_character_id,
            c.project_id,
            c.name,
            c.personality,
            c.background,
            c.status,
            c.current_state,
            c.avatar_url,
            c.traits,
            c.organization_type,
            c.organization_purpose,
            o.id AS legacy_organization_id,
            o.parent_org_id AS legacy_parent_org_id,
            o.level,
            o.power_level,
            o.member_count,
            o.location,
            o.motto,
            o.color
        FROM characters c
        LEFT JOIN organizations o ON o.character_id = c.id
        WHERE c.is_organization = true
        """
    )).mappings().all()


def _backfill_organization_entities() -> dict[str, str]:
    bind = op.get_bind()
    char_to_org_entity: dict[str, str] = {}

    for row in _legacy_org_rows():
        entity_id = str(uuid.uuid4())
        char_to_org_entity[row["legacy_character_id"]] = entity_id
        bind.execute(sa.text(
            """
            INSERT INTO organization_entities (
                id, project_id, name, normalized_name, personality, background, status,
                current_state, avatar_url, traits, organization_type, organization_purpose,
                legacy_character_id, legacy_organization_id, legacy_parent_org_id,
                level, power_level, member_count, location, motto, color, source
            ) VALUES (
                :id, :project_id, :name, :normalized_name, :personality, :background, :status,
                :current_state, :avatar_url, :traits, :organization_type, :organization_purpose,
                :legacy_character_id, :legacy_organization_id, :legacy_parent_org_id,
                :level, :power_level, :member_count, :location, :motto, :color, 'legacy'
            )
            """
        ), {
            "id": entity_id,
            "project_id": row["project_id"],
            "name": row["name"],
            "normalized_name": (row["name"] or "").strip().lower(),
            "personality": row["personality"],
            "background": row["background"],
            "status": row["status"] or "active",
            "current_state": row["current_state"],
            "avatar_url": row["avatar_url"],
            "traits": row["traits"],
            "organization_type": row["organization_type"],
            "organization_purpose": row["organization_purpose"],
            "legacy_character_id": row["legacy_character_id"],
            "legacy_organization_id": row["legacy_organization_id"],
            "legacy_parent_org_id": row["legacy_parent_org_id"],
            "level": row["level"],
            "power_level": row["power_level"],
            "member_count": row["member_count"],
            "location": row["location"],
            "motto": row["motto"],
            "color": row["color"],
        })

        if row["legacy_organization_id"]:
            bind.execute(sa.text(
                "UPDATE organizations SET organization_entity_id = :entity_id WHERE id = :legacy_organization_id"
            ), {"entity_id": entity_id, "legacy_organization_id": row["legacy_organization_id"]})
            bind.execute(sa.text(
                "UPDATE organization_members SET organization_entity_id = :entity_id WHERE organization_id = :legacy_organization_id"
            ), {"entity_id": entity_id, "legacy_organization_id": row["legacy_organization_id"]})

    bind.execute(sa.text(
        """
        UPDATE organization_entities child
        SET parent_org_id = parent.id
        FROM organization_entities parent
        WHERE child.legacy_parent_org_id = parent.legacy_organization_id
        """
    ))
    return char_to_org_entity


def _backfill_entity_relationships(char_to_org_entity: dict[str, str]) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        """
        SELECT id, project_id, character_from_id, character_to_id, relationship_type_id,
               relationship_name, intimacy_level, status, description, started_at,
               ended_at, source, created_at, updated_at
        FROM character_relationships
        """
    )).mappings().all()

    for row in rows:
        from_is_org = row["character_from_id"] in char_to_org_entity
        to_is_org = row["character_to_id"] in char_to_org_entity
        bind.execute(sa.text(
            """
            INSERT INTO entity_relationships (
                id, project_id, from_entity_type, from_entity_id, to_entity_type, to_entity_id,
                relationship_type_id, relationship_name, intimacy_level, status, description,
                started_at, ended_at, source, legacy_character_relationship_id, created_at, updated_at
            ) VALUES (
                :id, :project_id, :from_entity_type, :from_entity_id, :to_entity_type, :to_entity_id,
                :relationship_type_id, :relationship_name, :intimacy_level, :status, :description,
                :started_at, :ended_at, :source, :legacy_character_relationship_id, :created_at, :updated_at
            )
            """
        ), {
            "id": str(uuid.uuid4()),
            "project_id": row["project_id"],
            "from_entity_type": "organization" if from_is_org else "character",
            "from_entity_id": char_to_org_entity.get(row["character_from_id"], row["character_from_id"]),
            "to_entity_type": "organization" if to_is_org else "character",
            "to_entity_id": char_to_org_entity.get(row["character_to_id"], row["character_to_id"]),
            "relationship_type_id": row["relationship_type_id"],
            "relationship_name": row["relationship_name"],
            "intimacy_level": row["intimacy_level"],
            "status": row["status"] or "active",
            "description": row["description"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "source": row["source"] or "legacy",
            "legacy_character_relationship_id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })


def upgrade() -> None:
    op.add_column('settings', sa.Column('default_reasoning_intensity', sa.String(length=20), server_default='auto', nullable=False, comment='默认推理强度'))
    op.add_column('settings', sa.Column('reasoning_overrides', sa.Text(), nullable=True, comment='推理强度覆盖(JSON)'))
    op.add_column('settings', sa.Column('allow_ai_entity_generation', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='是否允许AI直接生成规范实体'))

    op.create_table('organization_entities',
        sa.Column('id', sa.String(length=36), nullable=False, comment='组织实体ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='组织名称'),
        sa.Column('normalized_name', sa.String(length=100), nullable=False, comment='规范化组织名称'),
        sa.Column('personality', sa.Text(), nullable=True, comment='组织特性'),
        sa.Column('background', sa.Text(), nullable=True, comment='组织背景'),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False, comment='状态'),
        sa.Column('current_state', sa.Text(), nullable=True, comment='组织当前状态'),
        sa.Column('avatar_url', sa.String(length=500), nullable=True, comment='头像URL'),
        sa.Column('traits', sa.Text(), nullable=True, comment='特征标签(JSON)'),
        sa.Column('organization_type', sa.String(length=100), nullable=True, comment='组织类型'),
        sa.Column('organization_purpose', sa.String(length=500), nullable=True, comment='组织目的'),
        sa.Column('parent_org_id', sa.String(length=36), nullable=True, comment='父组织实体ID'),
        sa.Column('legacy_parent_org_id', sa.String(length=36), nullable=True, comment='迁移前父组织ID'),
        sa.Column('level', sa.Integer(), nullable=True, comment='组织层级'),
        sa.Column('power_level', sa.Integer(), nullable=True, comment='势力等级'),
        sa.Column('member_count', sa.Integer(), nullable=True, comment='成员数量'),
        sa.Column('location', sa.Text(), nullable=True, comment='所在地'),
        sa.Column('motto', sa.String(length=200), nullable=True, comment='宗旨/口号'),
        sa.Column('color', sa.String(length=100), nullable=True, comment='代表颜色'),
        sa.Column('legacy_character_id', sa.String(length=36), nullable=True, comment='迁移前承载组织的角色ID'),
        sa.Column('legacy_organization_id', sa.String(length=36), nullable=True, comment='迁移前组织详情记录ID'),
        sa.Column('source', sa.String(length=20), server_default='legacy', nullable=False, comment='来源'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['parent_org_id'], ['organization_entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('legacy_character_id'),
        sa.UniqueConstraint('legacy_organization_id')
    )
    op.create_index('idx_org_entities_project_name', 'organization_entities', ['project_id', 'normalized_name'], unique=False)
    op.create_index('idx_org_entities_project_status', 'organization_entities', ['project_id', 'status'], unique=False)
    op.create_index(op.f('ix_organization_entities_legacy_character_id'), 'organization_entities', ['legacy_character_id'], unique=True)
    op.create_index(op.f('ix_organization_entities_legacy_organization_id'), 'organization_entities', ['legacy_organization_id'], unique=True)
    op.create_index(op.f('ix_organization_entities_parent_org_id'), 'organization_entities', ['parent_org_id'], unique=False)
    op.create_index(op.f('ix_organization_entities_project_id'), 'organization_entities', ['project_id'], unique=False)

    op.execute('ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_character_id_fkey')
    op.add_column('organizations', sa.Column('organization_entity_id', sa.String(length=36), nullable=True, comment='拆分后的组织实体ID'))
    op.create_index(op.f('ix_organizations_organization_entity_id'), 'organizations', ['organization_entity_id'], unique=True)
    op.create_foreign_key('fk_organizations_organization_entity_id', 'organizations', 'organization_entities', ['organization_entity_id'], ['id'], ondelete='SET NULL')
    op.add_column('organization_members', sa.Column('organization_entity_id', sa.String(length=36), nullable=True, comment='组织实体ID'))
    op.create_index(op.f('ix_organization_members_organization_entity_id'), 'organization_members', ['organization_entity_id'], unique=False)
    op.create_foreign_key('fk_organization_members_organization_entity_id', 'organization_members', 'organization_entities', ['organization_entity_id'], ['id'], ondelete='CASCADE')

    op.create_table('entity_relationships',
        sa.Column('id', sa.String(length=36), nullable=False, comment='实体关系ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('from_entity_type', sa.String(length=20), nullable=False, comment='起点类型'),
        sa.Column('from_entity_id', sa.String(length=36), nullable=False, comment='起点实体ID'),
        sa.Column('to_entity_type', sa.String(length=20), nullable=False, comment='终点类型'),
        sa.Column('to_entity_id', sa.String(length=36), nullable=False, comment='终点实体ID'),
        sa.Column('relationship_type_id', sa.Integer(), nullable=True, comment='关系类型ID'),
        sa.Column('relationship_name', sa.String(length=100), nullable=True, comment='自定义关系名称'),
        sa.Column('intimacy_level', sa.Integer(), nullable=True, comment='亲密度'),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False, comment='状态'),
        sa.Column('description', sa.Text(), nullable=True, comment='关系详细描述'),
        sa.Column('started_at', sa.String(length=100), nullable=True, comment='关系开始时间'),
        sa.Column('ended_at', sa.String(length=100), nullable=True, comment='关系结束时间'),
        sa.Column('source', sa.String(length=20), nullable=True, comment='来源'),
        sa.Column('legacy_character_relationship_id', sa.String(length=36), nullable=True, comment='迁移前角色关系ID'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['relationship_type_id'], ['relationship_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('legacy_character_relationship_id')
    )
    op.create_index('idx_entity_relationships_from', 'entity_relationships', ['from_entity_type', 'from_entity_id'], unique=False)
    op.create_index('idx_entity_relationships_project_status', 'entity_relationships', ['project_id', 'status'], unique=False)
    op.create_index('idx_entity_relationships_to', 'entity_relationships', ['to_entity_type', 'to_entity_id'], unique=False)
    op.create_index(op.f('ix_entity_relationships_legacy_character_relationship_id'), 'entity_relationships', ['legacy_character_relationship_id'], unique=True)
    op.create_index(op.f('ix_entity_relationships_project_id'), 'entity_relationships', ['project_id'], unique=False)
    op.create_index(op.f('ix_entity_relationships_relationship_type_id'), 'entity_relationships', ['relationship_type_id'], unique=False)

    char_to_org_entity = _backfill_organization_entities()
    _backfill_entity_relationships(char_to_org_entity)
    op.alter_column(
        'organization_members',
        'organization_entity_id',
        existing_type=sa.String(length=36),
        nullable=False,
        existing_comment='组织实体ID',
    )

    op.create_table('extraction_runs',
        sa.Column('id', sa.String(length=36), nullable=False, comment='抽取运行ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('chapter_id', sa.String(length=36), nullable=True, comment='章节ID'),
        sa.Column('trigger_source', sa.String(length=50), nullable=False, comment='触发来源'),
        sa.Column('pipeline_version', sa.String(length=50), nullable=False, comment='抽取管线版本'),
        sa.Column('schema_version', sa.String(length=50), nullable=False, comment='结构化输出Schema版本'),
        sa.Column('prompt_hash', sa.String(length=128), nullable=True, comment='提示词哈希'),
        sa.Column('content_hash', sa.String(length=128), nullable=False, comment='正文内容哈希'),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False, comment='状态'),
        sa.Column('provider', sa.String(length=50), nullable=True, comment='AI提供商'),
        sa.Column('model', sa.String(length=100), nullable=True, comment='模型名称'),
        sa.Column('reasoning_intensity', sa.String(length=20), nullable=True, comment='推理强度'),
        sa.Column('raw_response', sa.JSON(), nullable=True, comment='模型原始响应'),
        sa.Column('metadata', sa.JSON(), nullable=True, comment='运行元数据'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('started_at', sa.DateTime(), nullable=True, comment='开始时间'),
        sa.Column('completed_at', sa.DateTime(), nullable=True, comment='完成时间'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_extraction_runs_project_content', 'extraction_runs', ['project_id', 'chapter_id', 'content_hash', 'schema_version', 'prompt_hash'], unique=False)
    op.create_index('idx_extraction_runs_project_status', 'extraction_runs', ['project_id', 'status'], unique=False)
    op.create_index(op.f('ix_extraction_runs_chapter_id'), 'extraction_runs', ['chapter_id'], unique=False)
    op.create_index(op.f('ix_extraction_runs_project_id'), 'extraction_runs', ['project_id'], unique=False)

    op.create_table('extraction_candidates',
        sa.Column('id', sa.String(length=36), nullable=False, comment='候选ID'),
        sa.Column('run_id', sa.String(length=36), nullable=False, comment='抽取运行ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('user_id', sa.String(length=100), nullable=False, comment='用户ID'),
        sa.Column('source_chapter_id', sa.String(length=36), nullable=True, comment='来源章节ID'),
        sa.Column('source_chapter_start_id', sa.String(length=36), nullable=True, comment='来源章节范围起点'),
        sa.Column('source_chapter_end_id', sa.String(length=36), nullable=True, comment='来源章节范围终点'),
        sa.Column('candidate_type', sa.String(length=50), nullable=False, comment='候选类型'),
        sa.Column('trigger_type', sa.String(length=50), nullable=False, comment='触发类型'),
        sa.Column('source_hash', sa.String(length=128), nullable=False, comment='来源哈希'),
        sa.Column('provider', sa.String(length=50), nullable=True, comment='AI提供商快照'),
        sa.Column('model', sa.String(length=100), nullable=True, comment='模型快照'),
        sa.Column('reasoning_intensity', sa.String(length=20), nullable=True, comment='推理强度快照'),
        sa.Column('display_name', sa.String(length=200), nullable=True, comment='展示名称'),
        sa.Column('normalized_name', sa.String(length=200), nullable=True, comment='规范化名称'),
        sa.Column('canonical_target_type', sa.String(length=20), nullable=True, comment='目标类型'),
        sa.Column('canonical_target_id', sa.String(length=36), nullable=True, comment='目标ID'),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False, comment='状态'),
        sa.Column('confidence', sa.Float(), nullable=False, comment='置信度'),
        sa.Column('evidence_text', sa.Text(), nullable=False, comment='证据原文'),
        sa.Column('source_start_offset', sa.Integer(), nullable=False, comment='起始偏移'),
        sa.Column('source_end_offset', sa.Integer(), nullable=False, comment='结束偏移'),
        sa.Column('source_chapter_number', sa.Integer(), nullable=True, comment='来源章节序号'),
        sa.Column('source_chapter_order', sa.Integer(), nullable=True, comment='来源章节内顺序'),
        sa.Column('valid_from_chapter_id', sa.String(length=36), nullable=True, comment='有效起点章节'),
        sa.Column('valid_from_chapter_order', sa.Integer(), nullable=True, comment='有效起点顺序'),
        sa.Column('valid_to_chapter_id', sa.String(length=36), nullable=True, comment='有效终点章节'),
        sa.Column('valid_to_chapter_order', sa.Integer(), nullable=True, comment='有效终点顺序'),
        sa.Column('story_time_label', sa.String(length=100), nullable=True, comment='故事时间标签'),
        sa.Column('payload', sa.JSON(), nullable=False, comment='规范化候选载荷'),
        sa.Column('raw_payload', sa.JSON(), nullable=True, comment='模型原始候选载荷'),
        sa.Column('merge_target_type', sa.String(length=50), nullable=True, comment='合并目标类型'),
        sa.Column('merge_target_id', sa.String(length=36), nullable=True, comment='合并目标ID'),
        sa.Column('reviewer_user_id', sa.String(length=100), nullable=True, comment='评审用户ID'),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True, comment='评审时间'),
        sa.Column('accepted_at', sa.DateTime(), nullable=True, comment='接受时间'),
        sa.Column('rejection_reason', sa.Text(), nullable=True, comment='拒绝原因'),
        sa.Column('supersedes_candidate_id', sa.String(length=36), nullable=True, comment='被替代候选ID'),
        sa.Column('rollback_of_candidate_id', sa.String(length=36), nullable=True, comment='回滚候选ID'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.CheckConstraint("canonical_target_type IS NULL OR canonical_target_type IN ('character', 'organization', 'career')", name='ck_extraction_candidates_canonical_target_type'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['extraction_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_chapter_start_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_chapter_end_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['valid_from_chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['valid_to_chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supersedes_candidate_id'], ['extraction_candidates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rollback_of_candidate_id'], ['extraction_candidates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_extraction_candidates_canonical', 'extraction_candidates', ['canonical_target_type', 'canonical_target_id'], unique=False)
    op.create_index('idx_extraction_candidates_project_type_status', 'extraction_candidates', ['project_id', 'candidate_type', 'status'], unique=False)
    op.create_index('idx_extraction_candidates_run_status', 'extraction_candidates', ['run_id', 'status'], unique=False)
    op.create_index('idx_extraction_candidates_source_hash', 'extraction_candidates', ['project_id', 'source_hash'], unique=False)
    op.create_index('idx_extraction_candidates_timeline', 'extraction_candidates', ['project_id', 'valid_from_chapter_id', 'valid_from_chapter_order'], unique=False)
    op.create_index(op.f('ix_extraction_candidates_project_id'), 'extraction_candidates', ['project_id'], unique=False)
    op.create_index(op.f('ix_extraction_candidates_run_id'), 'extraction_candidates', ['run_id'], unique=False)
    op.create_index(op.f('ix_extraction_candidates_source_chapter_id'), 'extraction_candidates', ['source_chapter_id'], unique=False)
    op.create_index(op.f('ix_extraction_candidates_user_id'), 'extraction_candidates', ['user_id'], unique=False)
    op.create_index(op.f('ix_extraction_candidates_valid_from_chapter_id'), 'extraction_candidates', ['valid_from_chapter_id'], unique=False)
    op.create_index(op.f('ix_extraction_candidates_valid_to_chapter_id'), 'extraction_candidates', ['valid_to_chapter_id'], unique=False)

    op.create_table('entity_provenance',
        sa.Column('id', sa.String(length=36), nullable=False, comment='来源ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('entity_type', sa.String(length=50), nullable=False, comment='实体类型'),
        sa.Column('entity_id', sa.String(length=36), nullable=False, comment='实体ID'),
        sa.Column('source_type', sa.String(length=50), nullable=False, comment='来源类型'),
        sa.Column('source_id', sa.String(length=36), nullable=True, comment='来源记录ID'),
        sa.Column('run_id', sa.String(length=36), nullable=True, comment='抽取运行ID'),
        sa.Column('candidate_id', sa.String(length=36), nullable=True, comment='候选ID'),
        sa.Column('chapter_id', sa.String(length=36), nullable=True, comment='章节ID'),
        sa.Column('claim_type', sa.String(length=50), nullable=False, comment='事实类型'),
        sa.Column('claim_payload', sa.JSON(), nullable=True, comment='事实载荷'),
        sa.Column('evidence_text', sa.Text(), nullable=True, comment='证据原文'),
        sa.Column('source_start', sa.Integer(), nullable=True, comment='证据起始字符偏移'),
        sa.Column('source_end', sa.Integer(), nullable=True, comment='证据结束字符偏移'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='置信度'),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False, comment='状态'),
        sa.Column('created_by', sa.String(length=100), nullable=True, comment='创建用户/系统'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['candidate_id'], ['extraction_candidates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['extraction_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_entity_provenance_entity', 'entity_provenance', ['entity_type', 'entity_id'], unique=False)
    op.create_index('idx_entity_provenance_project_claim', 'entity_provenance', ['project_id', 'claim_type', 'status'], unique=False)
    op.create_index(op.f('ix_entity_provenance_candidate_id'), 'entity_provenance', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_entity_provenance_chapter_id'), 'entity_provenance', ['chapter_id'], unique=False)
    op.create_index(op.f('ix_entity_provenance_project_id'), 'entity_provenance', ['project_id'], unique=False)
    op.create_index(op.f('ix_entity_provenance_run_id'), 'entity_provenance', ['run_id'], unique=False)

    op.create_table('entity_aliases',
        sa.Column('id', sa.String(length=36), nullable=False, comment='别名ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('entity_type', sa.String(length=50), nullable=False, comment='实体类型'),
        sa.Column('entity_id', sa.String(length=36), nullable=False, comment='实体ID'),
        sa.Column('alias', sa.String(length=200), nullable=False, comment='别名'),
        sa.Column('normalized_alias', sa.String(length=200), nullable=False, comment='规范化别名'),
        sa.Column('source', sa.String(length=50), server_default='manual', nullable=False, comment='来源'),
        sa.Column('provenance_id', sa.String(length=36), nullable=True, comment='来源ID'),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False, comment='状态'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['provenance_id'], ['entity_provenance.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_entity_aliases_entity', 'entity_aliases', ['entity_type', 'entity_id', 'status'], unique=False)
    op.create_index('idx_entity_aliases_lookup', 'entity_aliases', ['project_id', 'normalized_alias', 'entity_type'], unique=False)
    op.create_index(op.f('ix_entity_aliases_project_id'), 'entity_aliases', ['project_id'], unique=False)
    op.create_index(op.f('ix_entity_aliases_provenance_id'), 'entity_aliases', ['provenance_id'], unique=False)

    op.create_table('relationship_timeline_events',
        sa.Column('id', sa.String(length=36), nullable=False, comment='时间线事件ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('relationship_id', sa.String(length=36), nullable=True, comment='实体关系ID'),
        sa.Column('organization_member_id', sa.String(length=36), nullable=True, comment='组织成员关系ID'),
        sa.Column('character_id', sa.String(length=36), nullable=True, comment='主体角色ID'),
        sa.Column('related_character_id', sa.String(length=36), nullable=True, comment='相关角色ID'),
        sa.Column('organization_entity_id', sa.String(length=36), nullable=True, comment='组织实体ID'),
        sa.Column('career_id', sa.String(length=36), nullable=True, comment='职业ID'),
        sa.Column('event_type', sa.String(length=50), nullable=False, comment='事件类型'),
        sa.Column('event_status', sa.String(length=20), server_default='active', nullable=False, comment='状态'),
        sa.Column('relationship_name', sa.String(length=100), nullable=True, comment='关系名称'),
        sa.Column('position', sa.String(length=100), nullable=True, comment='组织职位'),
        sa.Column('rank', sa.Integer(), nullable=True, comment='职位/等级'),
        sa.Column('career_stage', sa.Integer(), nullable=True, comment='职业阶段'),
        sa.Column('story_time_label', sa.String(length=100), nullable=True, comment='故事内时间标签'),
        sa.Column('source_chapter_id', sa.String(length=36), nullable=True, comment='来源章节ID'),
        sa.Column('source_chapter_order', sa.Integer(), nullable=True, comment='来源章节内顺序'),
        sa.Column('valid_from_chapter_id', sa.String(length=36), nullable=True, comment='有效起点章节'),
        sa.Column('valid_from_chapter_order', sa.Integer(), nullable=True, comment='有效起点顺序'),
        sa.Column('valid_to_chapter_id', sa.String(length=36), nullable=True, comment='有效终点章节'),
        sa.Column('valid_to_chapter_order', sa.Integer(), nullable=True, comment='有效终点顺序'),
        sa.Column('source_start_offset', sa.Integer(), nullable=True, comment='证据起始字符偏移'),
        sa.Column('source_end_offset', sa.Integer(), nullable=True, comment='证据结束字符偏移'),
        sa.Column('evidence_text', sa.Text(), nullable=True, comment='证据原文'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='置信度'),
        sa.Column('provenance_id', sa.String(length=36), nullable=True, comment='来源ID'),
        sa.Column('supersedes_event_id', sa.String(length=36), nullable=True, comment='被替代事件ID'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['career_id'], ['careers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['valid_from_chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['valid_to_chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_entity_id'], ['organization_entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_member_id'], ['organization_members.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['provenance_id'], ['entity_provenance.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['related_character_id'], ['characters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['relationship_id'], ['entity_relationships.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supersedes_event_id'], ['relationship_timeline_events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_relationship_timeline_project_position', 'relationship_timeline_events', ['project_id', 'valid_from_chapter_id', 'valid_from_chapter_order'], unique=False)
    op.create_index('idx_relationship_timeline_type_status', 'relationship_timeline_events', ['project_id', 'event_type', 'event_status'], unique=False)
    op.create_index(op.f('ix_relationship_timeline_events_career_id'), 'relationship_timeline_events', ['career_id'], unique=False)
    op.create_index(op.f('ix_relationship_timeline_events_organization_entity_id'), 'relationship_timeline_events', ['organization_entity_id'], unique=False)
    op.create_index(op.f('ix_relationship_timeline_events_project_id'), 'relationship_timeline_events', ['project_id'], unique=False)
    op.create_index(op.f('ix_relationship_timeline_events_relationship_id'), 'relationship_timeline_events', ['relationship_id'], unique=False)
    op.create_index(op.f('ix_relationship_timeline_events_valid_from_chapter_id'), 'relationship_timeline_events', ['valid_from_chapter_id'], unique=False)
    op.create_index(op.f('ix_relationship_timeline_events_valid_to_chapter_id'), 'relationship_timeline_events', ['valid_to_chapter_id'], unique=False)

    op.create_table('world_setting_results',
        sa.Column('id', sa.String(length=36), nullable=False, comment='世界观结果ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('run_id', sa.String(length=36), nullable=True, comment='相关抽取/生成运行ID'),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False, comment='状态'),
        sa.Column('world_time_period', sa.Text(), nullable=True, comment='时间背景'),
        sa.Column('world_location', sa.Text(), nullable=True, comment='地理位置'),
        sa.Column('world_atmosphere', sa.Text(), nullable=True, comment='氛围基调'),
        sa.Column('world_rules', sa.Text(), nullable=True, comment='世界规则'),
        sa.Column('prompt', sa.Text(), nullable=True, comment='生成提示词'),
        sa.Column('provider', sa.String(length=50), nullable=True, comment='AI提供商'),
        sa.Column('model', sa.String(length=100), nullable=True, comment='模型名称'),
        sa.Column('reasoning_intensity', sa.String(length=20), nullable=True, comment='推理强度'),
        sa.Column('raw_result', sa.JSON(), nullable=True, comment='原始结果'),
        sa.Column('source_type', sa.String(length=50), server_default='ai', nullable=False, comment='来源类型'),
        sa.Column('accepted_at', sa.DateTime(), nullable=True, comment='接受时间'),
        sa.Column('accepted_by', sa.String(length=100), nullable=True, comment='接受用户ID'),
        sa.Column('supersedes_result_id', sa.String(length=36), nullable=True, comment='被替代结果ID'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['extraction_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supersedes_result_id'], ['world_setting_results.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_world_setting_results_project_created', 'world_setting_results', ['project_id', 'created_at'], unique=False)
    op.create_index('idx_world_setting_results_project_status', 'world_setting_results', ['project_id', 'status'], unique=False)
    op.create_index(op.f('ix_world_setting_results_project_id'), 'world_setting_results', ['project_id'], unique=False)
    op.create_index(op.f('ix_world_setting_results_run_id'), 'world_setting_results', ['run_id'], unique=False)

    op.execute('DELETE FROM characters WHERE is_organization = true')
    op.drop_column('organizations', 'color')
    op.drop_column('organizations', 'motto')
    op.drop_column('organizations', 'location')
    op.drop_column('organizations', 'member_count')
    op.drop_column('organizations', 'power_level')
    op.drop_column('organizations', 'level')
    op.drop_column('organizations', 'parent_org_id')
    op.drop_column('characters', 'organization_members')
    op.drop_column('characters', 'organization_purpose')
    op.drop_column('characters', 'organization_type')
    op.drop_column('characters', 'is_organization')


def downgrade() -> None:
    op.add_column('characters', sa.Column('is_organization', sa.Boolean(), nullable=True, comment='是否为组织'))
    op.add_column('characters', sa.Column('organization_type', sa.String(length=100), nullable=True, comment='组织类型'))
    op.add_column('characters', sa.Column('organization_purpose', sa.String(length=500), nullable=True, comment='组织目的'))
    op.add_column('characters', sa.Column('organization_members', sa.Text(), nullable=True, comment='组织成员(JSON)'))
    op.add_column('organizations', sa.Column('parent_org_id', sa.String(length=36), nullable=True, comment='父组织ID'))
    op.add_column('organizations', sa.Column('level', sa.Integer(), nullable=True, comment='组织层级'))
    op.add_column('organizations', sa.Column('power_level', sa.Integer(), nullable=True, comment='势力等级'))
    op.add_column('organizations', sa.Column('member_count', sa.Integer(), nullable=True, comment='成员数量'))
    op.add_column('organizations', sa.Column('location', sa.Text(), nullable=True, comment='所在地'))
    op.add_column('organizations', sa.Column('motto', sa.String(length=200), nullable=True, comment='宗旨/口号'))
    op.add_column('organizations', sa.Column('color', sa.String(length=100), nullable=True, comment='代表颜色'))
    op.drop_table('world_setting_results')
    op.drop_table('relationship_timeline_events')
    op.drop_table('entity_aliases')
    op.drop_table('entity_provenance')
    op.drop_table('extraction_candidates')
    op.drop_table('extraction_runs')
    op.drop_table('entity_relationships')
    op.drop_constraint('fk_organization_members_organization_entity_id', 'organization_members', type_='foreignkey')
    op.drop_index(op.f('ix_organization_members_organization_entity_id'), table_name='organization_members')
    op.drop_column('organization_members', 'organization_entity_id')
    op.drop_constraint('fk_organizations_organization_entity_id', 'organizations', type_='foreignkey')
    op.drop_index(op.f('ix_organizations_organization_entity_id'), table_name='organizations')
    op.drop_column('organizations', 'organization_entity_id')
    op.drop_table('organization_entities')
    op.drop_column('settings', 'allow_ai_entity_generation')
    op.drop_column('settings', 'reasoning_overrides')
    op.drop_column('settings', 'default_reasoning_intensity')
