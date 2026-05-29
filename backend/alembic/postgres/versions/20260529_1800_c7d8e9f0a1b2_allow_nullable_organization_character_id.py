"""allow nullable organization character id

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-05-29 18:00:00

"""
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "organizations",
        "character_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "organizations",
        "character_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
