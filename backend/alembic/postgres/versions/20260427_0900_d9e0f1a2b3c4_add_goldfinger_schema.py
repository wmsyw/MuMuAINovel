"""add goldfinger schema

Revision ID: d9e0f1a2b3c4
Revises: b7c8d9e0f1a2
Create Date: 2026-04-27 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GOLDFINGER_STATUS_CONSTRAINT = "status IN ('latent', 'active', 'sealed', 'cooldown', 'upgrading', 'lost', 'completed', 'unknown')"


def upgrade() -> None:
    op.create_table('goldfingers',
        sa.Column('id', sa.String(length=36), nullable=False, comment='金手指ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('name', sa.String(length=200), nullable=False, comment='名称'),
        sa.Column('normalized_name', sa.String(length=200), nullable=False, comment='规范化名称'),
        sa.Column('owner_character_id', sa.String(length=36), nullable=True, comment='拥有者角色ID'),
        sa.Column('owner_character_name', sa.String(length=200), nullable=True, comment='拥有者角色名称快照'),
        sa.Column('type', sa.String(length=50), nullable=True, comment='类型'),
        sa.Column('status', sa.String(length=20), server_default='unknown', nullable=False, comment='状态'),
        sa.Column('summary', sa.Text(), nullable=True, comment='概要'),
        sa.Column('rules', sa.JSON(), nullable=True, comment='规则(JSON)'),
        sa.Column('tasks', sa.JSON(), nullable=True, comment='任务(JSON)'),
        sa.Column('rewards', sa.JSON(), nullable=True, comment='奖励(JSON)'),
        sa.Column('limits', sa.JSON(), nullable=True, comment='限制(JSON)'),
        sa.Column('trigger_conditions', sa.JSON(), nullable=True, comment='触发条件(JSON)'),
        sa.Column('cooldown', sa.JSON(), nullable=True, comment='冷却信息(JSON)'),
        sa.Column('aliases', sa.JSON(), nullable=True, comment='别名(JSON)'),
        sa.Column('metadata', sa.JSON(), nullable=True, comment='元数据(JSON)'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.Column('created_by', sa.String(length=100), nullable=True, comment='创建用户/系统'),
        sa.Column('updated_by', sa.String(length=100), nullable=True, comment='更新用户/系统'),
        sa.Column('source', sa.String(length=50), server_default='manual', nullable=False, comment='来源'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='置信度'),
        sa.Column('last_source_chapter_id', sa.String(length=36), nullable=True, comment='最后来源章节ID'),
        sa.CheckConstraint(GOLDFINGER_STATUS_CONSTRAINT, name='ck_goldfingers_status'),
        sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['last_source_chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_character_id'], ['characters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.user_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_goldfingers_owner_status', 'goldfingers', ['owner_character_id', 'status'], unique=False)
    op.create_index('idx_goldfingers_project_name', 'goldfingers', ['project_id', 'normalized_name'], unique=False)
    op.create_index('idx_goldfingers_project_status', 'goldfingers', ['project_id', 'status'], unique=False)
    op.create_index(op.f('ix_goldfingers_created_by'), 'goldfingers', ['created_by'], unique=False)
    op.create_index(op.f('ix_goldfingers_last_source_chapter_id'), 'goldfingers', ['last_source_chapter_id'], unique=False)
    op.create_index(op.f('ix_goldfingers_owner_character_id'), 'goldfingers', ['owner_character_id'], unique=False)
    op.create_index(op.f('ix_goldfingers_project_id'), 'goldfingers', ['project_id'], unique=False)
    op.create_index(op.f('ix_goldfingers_updated_by'), 'goldfingers', ['updated_by'], unique=False)

    op.create_table('goldfinger_history_events',
        sa.Column('id', sa.String(length=36), nullable=False, comment='金手指历史事件ID'),
        sa.Column('goldfinger_id', sa.String(length=36), nullable=False, comment='金手指ID'),
        sa.Column('project_id', sa.String(length=36), nullable=False, comment='项目ID'),
        sa.Column('chapter_id', sa.String(length=36), nullable=True, comment='章节ID'),
        sa.Column('event_type', sa.String(length=50), nullable=False, comment='事件类型'),
        sa.Column('old_value', sa.JSON(), nullable=True, comment='旧值(JSON)'),
        sa.Column('new_value', sa.JSON(), nullable=True, comment='新值(JSON)'),
        sa.Column('evidence_excerpt', sa.Text(), nullable=True, comment='证据摘录'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='置信度'),
        sa.Column('source_type', sa.String(length=50), nullable=True, comment='来源类型'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['goldfinger_id'], ['goldfingers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_goldfinger_history_goldfinger_created', 'goldfinger_history_events', ['goldfinger_id', 'created_at'], unique=False)
    op.create_index('idx_goldfinger_history_project_type', 'goldfinger_history_events', ['project_id', 'event_type'], unique=False)
    op.create_index(op.f('ix_goldfinger_history_events_chapter_id'), 'goldfinger_history_events', ['chapter_id'], unique=False)
    op.create_index(op.f('ix_goldfinger_history_events_goldfinger_id'), 'goldfinger_history_events', ['goldfinger_id'], unique=False)
    op.create_index(op.f('ix_goldfinger_history_events_project_id'), 'goldfinger_history_events', ['project_id'], unique=False)

    op.add_column('extraction_candidates', sa.Column('review_required_reason', sa.Text(), nullable=True, comment='需要人工评审原因'))


def downgrade() -> None:
    op.drop_column('extraction_candidates', 'review_required_reason')
    op.drop_table('goldfinger_history_events')
    op.drop_table('goldfingers')
