"""add character card fields

Revision ID: f8a9b0c1d2e3
Revises: d6e7f8a9b0c1
Create Date: 2026-05-22 13:02:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("writing_notes", sa.Text(), nullable=True, comment="作者私有写作笔记，不注入AI上下文"))
        batch_op.add_column(sa.Column("speech_patterns", sa.Text(), nullable=True, comment="语言风格、口头禅、语气说明"))
        batch_op.add_column(sa.Column("motivations", sa.Text(), nullable=True, comment="核心动机、目标与欲望"))
        batch_op.add_column(sa.Column("arc_summary", sa.Text(), nullable=True, comment="角色成长/变化弧线摘要"))
        batch_op.add_column(sa.Column("card_version", sa.Integer(), server_default="1", nullable=False, comment="角色卡JSON版本号"))


def downgrade() -> None:
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.drop_column("card_version")
        batch_op.drop_column("arc_summary")
        batch_op.drop_column("motivations")
        batch_op.drop_column("speech_patterns")
        batch_op.drop_column("writing_notes")
