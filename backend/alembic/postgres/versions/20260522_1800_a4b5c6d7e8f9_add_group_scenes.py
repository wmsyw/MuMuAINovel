"""add group scenes

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-05-22 18:00:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_scenes",
        sa.Column("id", sa.String(length=36), nullable=False, comment="群像场景ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("title", sa.String(length=200), nullable=False, comment="场景标题"),
        sa.Column("scenario", sa.Text(), nullable=False, comment="场景目标/背景"),
        sa.Column("participant_character_ids", sa.JSON(), nullable=False, comment="参与角色ID列表"),
        sa.Column("selected_voice_persona_id", sa.String(length=36), nullable=True, comment="选用旁白声音画像ID"),
        sa.Column("selected_lore_ids", sa.JSON(), nullable=False, comment="选用Lorebook条目ID列表"),
        sa.Column("prompt_context", sa.Text(), server_default="", nullable=False, comment="作者选择的额外提示上下文"),
        sa.Column("draft_text", sa.Text(), server_default="", nullable=False, comment="场景对话草稿"),
        sa.Column("prompt_trace", sa.JSON(), nullable=False, comment="确定性Prompt上下文追踪"),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False, comment="状态: draft/archived"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.CheckConstraint("status IN ('draft', 'archived')", name="ck_group_scenes_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["selected_voice_persona_id"], ["voice_personas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_group_scenes_project_id", "group_scenes", ["project_id"], unique=False)
    op.create_index("ix_group_scenes_user_id", "group_scenes", ["user_id"], unique=False)
    op.create_index("ix_group_scenes_selected_voice_persona_id", "group_scenes", ["selected_voice_persona_id"], unique=False)
    op.create_index("idx_group_scenes_project_user_updated", "group_scenes", ["project_id", "user_id", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_group_scenes_project_user_updated", table_name="group_scenes")
    op.drop_index("ix_group_scenes_selected_voice_persona_id", table_name="group_scenes")
    op.drop_index("ix_group_scenes_user_id", table_name="group_scenes")
    op.drop_index("ix_group_scenes_project_id", table_name="group_scenes")
    op.drop_table("group_scenes")
