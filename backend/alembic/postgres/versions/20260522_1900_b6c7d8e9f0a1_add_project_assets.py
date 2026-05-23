"""Add project local assets.

Revision ID: b6c7d8e9f0a1
Revises: a4b5c6d7e8f9
Create Date: 2026-05-22 19:00:00
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "project_assets",
        sa.Column("id", sa.String(length=36), nullable=False, comment="本地资源ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("asset_type", sa.String(length=30), nullable=False, comment="资源类型: avatar/background/sprite"),
        sa.Column("display_name", sa.String(length=200), nullable=False, comment="展示名称"),
        sa.Column("original_filename", sa.String(length=255), nullable=False, comment="原始上传文件名"),
        sa.Column("storage_key", sa.String(length=500), nullable=False, comment="相对存储路径"),
        sa.Column("storage_filename", sa.String(length=255), nullable=False, comment="服务端生成文件名"),
        sa.Column("mime_type", sa.String(length=100), nullable=False, comment="MIME类型"),
        sa.Column("file_size", sa.Integer(), nullable=False, comment="文件大小（字节）"),
        sa.Column("content_hash", sa.String(length=64), nullable=False, comment="文件SHA256"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.CheckConstraint("asset_type IN ('avatar', 'background', 'sprite')", name="ck_project_assets_asset_type"),
        sa.CheckConstraint("file_size >= 0", name="ck_project_assets_file_size_non_negative"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_project_assets_project_id", "project_assets", ["project_id"], unique=False)
    op.create_index("ix_project_assets_user_id", "project_assets", ["user_id"], unique=False)
    op.create_index("ix_project_assets_content_hash", "project_assets", ["content_hash"], unique=False)
    op.create_index("idx_project_assets_project_user_type_created", "project_assets", ["project_id", "user_id", "asset_type", "created_at"], unique=False)
    op.create_index("idx_project_assets_project_hash", "project_assets", ["project_id", "content_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_project_assets_project_hash", table_name="project_assets")
    op.drop_index("idx_project_assets_project_user_type_created", table_name="project_assets")
    op.drop_index("ix_project_assets_content_hash", table_name="project_assets")
    op.drop_index("ix_project_assets_user_id", table_name="project_assets")
    op.drop_index("ix_project_assets_project_id", table_name="project_assets")
    op.drop_table("project_assets")
