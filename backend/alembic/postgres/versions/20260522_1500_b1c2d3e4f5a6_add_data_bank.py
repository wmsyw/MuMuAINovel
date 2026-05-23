"""add data bank tables

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-05-22 15:00:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_bank_items",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Data Bank条目ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("title", sa.String(length=200), nullable=False, comment="条目标题"),
        sa.Column("source_type", sa.String(length=30), nullable=False, comment="来源类型: snippet/upload"),
        sa.Column("filename", sa.String(length=255), nullable=True, comment="上传文件名"),
        sa.Column("content_type", sa.String(length=100), nullable=True, comment="上传MIME类型"),
        sa.Column("content_hash", sa.String(length=64), nullable=False, comment="原文SHA256"),
        sa.Column("text_content", sa.Text(), nullable=False, comment="本地原文内容"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, comment="切片数量"),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="条目元数据(JSON)"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.CheckConstraint("source_type IN ('snippet', 'upload')", name="ck_data_bank_items_source_type"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "data_bank_chunks",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Data Bank切片ID"),
        sa.Column("item_id", sa.String(length=36), nullable=False, comment="条目ID"),
        sa.Column("project_id", sa.String(length=36), nullable=False, comment="项目ID"),
        sa.Column("user_id", sa.String(length=100), nullable=False, comment="服务端用户ID"),
        sa.Column("chunk_index", sa.Integer(), nullable=False, comment="条目内切片序号"),
        sa.Column("content", sa.Text(), nullable=False, comment="切片文本"),
        sa.Column("char_start", sa.Integer(), nullable=False, comment="原文起始字符偏移"),
        sa.Column("char_end", sa.Integer(), nullable=False, comment="原文结束字符偏移"),
        sa.Column("content_hash", sa.String(length=64), nullable=False, comment="切片SHA256"),
        sa.Column("metadata", sa.JSON(), nullable=True, comment="切片元数据(JSON)"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.ForeignKeyConstraint(["item_id"], ["data_bank_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_bank_items_project_id", "data_bank_items", ["project_id"], unique=False)
    op.create_index("ix_data_bank_items_user_id", "data_bank_items", ["user_id"], unique=False)
    op.create_index("ix_data_bank_items_content_hash", "data_bank_items", ["content_hash"], unique=False)
    op.create_index("idx_data_bank_items_project_user_created", "data_bank_items", ["project_id", "user_id", "created_at"], unique=False)
    op.create_index("idx_data_bank_items_project_hash", "data_bank_items", ["project_id", "content_hash"], unique=False)
    op.create_index("ix_data_bank_chunks_item_id", "data_bank_chunks", ["item_id"], unique=False)
    op.create_index("ix_data_bank_chunks_project_id", "data_bank_chunks", ["project_id"], unique=False)
    op.create_index("ix_data_bank_chunks_user_id", "data_bank_chunks", ["user_id"], unique=False)
    op.create_index("ix_data_bank_chunks_content_hash", "data_bank_chunks", ["content_hash"], unique=False)
    op.create_index("idx_data_bank_chunks_project_user_item", "data_bank_chunks", ["project_id", "user_id", "item_id"], unique=False)
    op.create_index("idx_data_bank_chunks_item_index", "data_bank_chunks", ["item_id", "chunk_index"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_data_bank_chunks_item_index", table_name="data_bank_chunks")
    op.drop_index("idx_data_bank_chunks_project_user_item", table_name="data_bank_chunks")
    op.drop_index("ix_data_bank_chunks_content_hash", table_name="data_bank_chunks")
    op.drop_index("ix_data_bank_chunks_user_id", table_name="data_bank_chunks")
    op.drop_index("ix_data_bank_chunks_project_id", table_name="data_bank_chunks")
    op.drop_index("ix_data_bank_chunks_item_id", table_name="data_bank_chunks")
    op.drop_index("idx_data_bank_items_project_hash", table_name="data_bank_items")
    op.drop_index("idx_data_bank_items_project_user_created", table_name="data_bank_items")
    op.drop_index("ix_data_bank_items_content_hash", table_name="data_bank_items")
    op.drop_index("ix_data_bank_items_user_id", table_name="data_bank_items")
    op.drop_index("ix_data_bank_items_project_id", table_name="data_bank_items")
    op.drop_table("data_bank_chunks")
    op.drop_table("data_bank_items")
