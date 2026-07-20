"""add inspiration templates

Revision ID: 2b3c4d5e6f70
Revises: f9a0b1c2d3e4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "2b3c4d5e6f70"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspiration_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("tags", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_inspiration_templates_user_id"), "inspiration_templates", ["user_id"], unique=False)
    op.create_index(op.f("ix_inspiration_templates_platform"), "inspiration_templates", ["platform"], unique=False)
    op.create_index("ix_inspiration_templates_category_system", "inspiration_templates", ["category", "is_system"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_inspiration_templates_category_system", table_name="inspiration_templates")
    op.drop_index(op.f("ix_inspiration_templates_platform"), table_name="inspiration_templates")
    op.drop_index(op.f("ix_inspiration_templates_user_id"), table_name="inspiration_templates")
    op.drop_table("inspiration_templates")
