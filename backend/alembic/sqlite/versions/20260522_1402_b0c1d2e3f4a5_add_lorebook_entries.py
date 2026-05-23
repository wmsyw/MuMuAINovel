"""add lorebook entries

Revision ID: b0c1d2e3f4a5
Revises: f8a9b0c1d2e3
Create Date: 2026-05-22 14:02:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lorebook_entries",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Lorebook条目ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("title", sa.String(length=200), nullable=False, comment="条目标题"),
        sa.Column("content", sa.Text(), nullable=False, comment="条目内容"),
        sa.Column("activation_keys", sa.JSON(), nullable=False, comment="激活关键词列表"),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False, comment="选择优先级，数值越高越靠前"),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False, comment="是否启用"),
        sa.Column("source_type", sa.String(length=50), server_default="manual", nullable=False, comment="来源类型：manual/imported/derived"),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="条目元数据(JSON)"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="更新时间"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("lorebook_entries", schema=None) as batch_op:
        batch_op.create_index("ix_lorebook_entries_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_lorebook_entries_user_id", ["user_id"], unique=False)
        batch_op.create_index("idx_lorebook_entries_project_user_priority", ["project_id", "user_id", "priority"], unique=False)
        batch_op.create_index("idx_lorebook_entries_project_enabled", ["project_id", "enabled"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("lorebook_entries", schema=None) as batch_op:
        batch_op.drop_index("idx_lorebook_entries_project_enabled")
        batch_op.drop_index("idx_lorebook_entries_project_user_priority")
        batch_op.drop_index("ix_lorebook_entries_user_id")
        batch_op.drop_index("ix_lorebook_entries_project_id")
    op.drop_table("lorebook_entries")
