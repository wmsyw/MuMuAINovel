"""add voice personas

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-05-22 17:02:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_personas",
        sa.Column("id", sa.String(length=36), nullable=False, comment="旁白声音画像ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("session_id", sa.String(length=36), nullable=True, comment="可选创作会话ID"),
        sa.Column("scope", sa.String(length=20), server_default="project", nullable=False, comment="作用域: project/session"),
        sa.Column("name", sa.String(length=120), nullable=False, comment="声音画像名称"),
        sa.Column("tone", sa.Text(), nullable=False, comment="叙述语气"),
        sa.Column("style", sa.Text(), nullable=False, comment="文风特征"),
        sa.Column("point_of_view", sa.Text(), nullable=False, comment="叙事视角"),
        sa.Column("constraints", sa.Text(), nullable=False, comment="写作约束"),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False, comment="显示顺序，数值越小越靠前"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False, comment="是否启用"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True, comment="更新时间"),
        sa.CheckConstraint("scope IN ('project', 'session')", name="ck_voice_personas_scope"),
        sa.CheckConstraint(
            "(scope = 'project' AND session_id IS NULL) OR (scope = 'session' AND session_id IS NOT NULL)",
            name="ck_voice_personas_scope_session",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("voice_personas", schema=None) as batch_op:
        batch_op.create_index("ix_voice_personas_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_voice_personas_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_voice_personas_session_id", ["session_id"], unique=False)
        batch_op.create_index("idx_voice_personas_project_user_scope_order", ["project_id", "user_id", "scope", "sort_order"], unique=False)
        batch_op.create_index("idx_voice_personas_session_user_order", ["session_id", "user_id", "sort_order"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("voice_personas", schema=None) as batch_op:
        batch_op.drop_index("idx_voice_personas_session_user_order")
        batch_op.drop_index("idx_voice_personas_project_user_scope_order")
        batch_op.drop_index("ix_voice_personas_session_id")
        batch_op.drop_index("ix_voice_personas_user_id")
        batch_op.drop_index("ix_voice_personas_project_id")
    op.drop_table("voice_personas")
