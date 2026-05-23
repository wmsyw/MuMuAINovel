"""add quick replies

Revision ID: d2e3f4a5b6c7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-22 16:00:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
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
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False, comment="是否启用"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.CheckConstraint("action_type = 'safe_snippet'", name="ck_quick_replies_action_type_safe_snippet"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quick_replies_project_id", "quick_replies", ["project_id"], unique=False)
    op.create_index("ix_quick_replies_user_id", "quick_replies", ["user_id"], unique=False)
    op.create_index("idx_quick_replies_project_user_order", "quick_replies", ["project_id", "user_id", "sort_order"], unique=False)
    op.create_index("idx_quick_replies_project_enabled", "quick_replies", ["project_id", "enabled"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_quick_replies_project_enabled", table_name="quick_replies")
    op.drop_index("idx_quick_replies_project_user_order", table_name="quick_replies")
    op.drop_index("ix_quick_replies_user_id", table_name="quick_replies")
    op.drop_index("ix_quick_replies_project_id", table_name="quick_replies")
    op.drop_table("quick_replies")
