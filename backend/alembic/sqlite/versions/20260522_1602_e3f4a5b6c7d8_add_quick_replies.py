"""add quick replies

Revision ID: e3f4a5b6c7d8
Revises: c1d2e3f4a5b6
Create Date: 2026-05-22 16:02:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quick_replies",
        sa.Column("id", sa.String(length=36), nullable=False, comment="快捷回复ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("label", sa.String(length=100), nullable=False, comment="按钮标签"),
        sa.Column("action_type", sa.String(length=30), server_default="safe_snippet", nullable=False, comment="动作类型，仅允许safe_snippet"),
        sa.Column("snippet", sa.Text(), nullable=False, comment="安全静态片段内容"),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False, comment="显示顺序，数值越小越靠前"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False, comment="是否启用"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="更新时间"),
        sa.CheckConstraint("action_type = 'safe_snippet'", name="ck_quick_replies_action_type_safe_snippet"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("quick_replies", schema=None) as batch_op:
        batch_op.create_index("ix_quick_replies_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_quick_replies_user_id", ["user_id"], unique=False)
        batch_op.create_index("idx_quick_replies_project_user_order", ["project_id", "user_id", "sort_order"], unique=False)
        batch_op.create_index("idx_quick_replies_project_enabled", ["project_id", "enabled"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("quick_replies", schema=None) as batch_op:
        batch_op.drop_index("idx_quick_replies_project_enabled")
        batch_op.drop_index("idx_quick_replies_project_user_order")
        batch_op.drop_index("ix_quick_replies_user_id")
        batch_op.drop_index("ix_quick_replies_project_id")
    op.drop_table("quick_replies")
