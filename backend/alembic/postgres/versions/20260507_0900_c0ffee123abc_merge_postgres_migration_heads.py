"""merge postgres migration heads

Revision ID: c0ffee123abc
Revises: abc12345, f1a2b3c4d5e6
Create Date: 2026-05-07 09:00:00

"""


# revision identifiers, used by Alembic.
revision = 'c0ffee123abc'
down_revision = ('abc12345', 'f1a2b3c4d5e6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
