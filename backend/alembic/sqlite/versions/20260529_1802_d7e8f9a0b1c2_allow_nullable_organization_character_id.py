"""allow nullable organization character id

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-05-29 18:02:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.alter_column(
            "character_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.alter_column(
            "character_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
