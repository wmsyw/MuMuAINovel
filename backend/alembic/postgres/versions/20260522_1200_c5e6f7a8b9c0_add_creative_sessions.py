"""add creative sessions

Revision ID: c5e6f7a8b9c0
Revises: b8c9d0e1f2a3
Create Date: 2026-05-22 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5e6f7a8b9c0"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "creative_sessions",
        sa.Column("id", sa.String(length=36), nullable=False, comment="会话ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("title", sa.String(length=200), nullable=False, comment="会话标题"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="状态: active/archived"),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="会话元数据(JSON)"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_creative_sessions_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_creative_sessions_project_id", "creative_sessions", ["project_id"], unique=False)
    op.create_index("ix_creative_sessions_user_id", "creative_sessions", ["user_id"], unique=False)
    op.create_index("idx_creative_sessions_project_user_updated", "creative_sessions", ["project_id", "user_id", "updated_at"], unique=False)

    op.create_table(
        "creative_session_messages",
        sa.Column("id", sa.String(length=36), nullable=False, comment="消息ID"),
        sa.Column("session_id", sa.String(length=36), nullable=False, comment="会话ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("role", sa.String(length=30), nullable=False, comment="消息角色: user/assistant/system/note"),
        sa.Column("content", sa.Text(), nullable=False, comment="消息内容"),
        sa.Column("position", sa.Integer(), nullable=False, comment="会话内顺序"),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="消息元数据(JSON)"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'note')", name="ck_creative_session_messages_role"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_creative_session_messages_project_id", "creative_session_messages", ["project_id"], unique=False)
    op.create_index("ix_creative_session_messages_session_id", "creative_session_messages", ["session_id"], unique=False)
    op.create_index("ix_creative_session_messages_user_id", "creative_session_messages", ["user_id"], unique=False)
    op.create_index("idx_creative_session_messages_session_position", "creative_session_messages", ["session_id", "position"], unique=False)
    op.create_index("idx_creative_session_messages_project_user_created", "creative_session_messages", ["project_id", "user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_creative_session_messages_project_user_created", table_name="creative_session_messages")
    op.drop_index("idx_creative_session_messages_session_position", table_name="creative_session_messages")
    op.drop_index("ix_creative_session_messages_user_id", table_name="creative_session_messages")
    op.drop_index("ix_creative_session_messages_session_id", table_name="creative_session_messages")
    op.drop_index("ix_creative_session_messages_project_id", table_name="creative_session_messages")
    op.drop_table("creative_session_messages")
    op.drop_index("idx_creative_sessions_project_user_updated", table_name="creative_sessions")
    op.drop_index("ix_creative_sessions_user_id", table_name="creative_sessions")
    op.drop_index("ix_creative_sessions_project_id", table_name="creative_sessions")
    op.drop_table("creative_sessions")
