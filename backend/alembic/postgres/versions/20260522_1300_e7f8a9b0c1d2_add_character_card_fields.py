"""add character card fields

Revision ID: e7f8a9b0c1d2
Revises: c5e6f7a8b9c0
Create Date: 2026-05-22 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "c5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("writing_notes", sa.Text(), nullable=True, comment="作者私有写作笔记，不注入AI上下文"))
    op.add_column("characters", sa.Column("speech_patterns", sa.Text(), nullable=True, comment="语言风格、口头禅、语气说明"))
    op.add_column("characters", sa.Column("motivations", sa.Text(), nullable=True, comment="核心动机、目标与欲望"))
    op.add_column("characters", sa.Column("arc_summary", sa.Text(), nullable=True, comment="角色成长/变化弧线摘要"))
    op.add_column("characters", sa.Column("card_version", sa.Integer(), server_default="1", nullable=False, comment="角色卡JSON版本号"))


def downgrade() -> None:
    op.drop_column("characters", "card_version")
    op.drop_column("characters", "arc_summary")
    op.drop_column("characters", "motivations")
    op.drop_column("characters", "speech_patterns")
    op.drop_column("characters", "writing_notes")
