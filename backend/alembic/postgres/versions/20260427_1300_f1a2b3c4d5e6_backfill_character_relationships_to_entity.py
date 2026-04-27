"""backfill character relationships to entity relationships

Revision ID: f1a2b3c4d5e6
Revises: d9e0f1a2b3c4
Create Date: 2026-04-27 13:00:00

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        """
        SELECT id, project_id, character_from_id, character_to_id, relationship_type_id,
               relationship_name, intimacy_level, status, description, started_at,
               ended_at, source, created_at, updated_at
        FROM character_relationships cr
        WHERE NOT EXISTS (
            SELECT 1 FROM entity_relationships er
            WHERE er.legacy_character_relationship_id = cr.id
        )
        """
    )).mappings().all()

    for row in rows:
        bind.execute(sa.text(
            """
            INSERT INTO entity_relationships (
                id, project_id, from_entity_type, from_entity_id, to_entity_type, to_entity_id,
                relationship_type_id, relationship_name, intimacy_level, status, description,
                started_at, ended_at, source, legacy_character_relationship_id, created_at, updated_at
            ) VALUES (
                :id, :project_id, 'character', :from_entity_id, 'character', :to_entity_id,
                :relationship_type_id, :relationship_name, :intimacy_level, :status, :description,
                :started_at, :ended_at, :source, :legacy_character_relationship_id, :created_at, :updated_at
            )
            """
        ), {
            "id": str(uuid.uuid4()),
            "project_id": row["project_id"],
            "from_entity_id": row["character_from_id"],
            "to_entity_id": row["character_to_id"],
            "relationship_type_id": row["relationship_type_id"],
            "relationship_name": row["relationship_name"],
            "intimacy_level": row["intimacy_level"],
            "status": row["status"] or "active",
            "description": row["description"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "source": row["source"] or "legacy",
            "legacy_character_relationship_id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM entity_relationships
        WHERE legacy_character_relationship_id IN (SELECT id FROM character_relationships)
        """
    )
