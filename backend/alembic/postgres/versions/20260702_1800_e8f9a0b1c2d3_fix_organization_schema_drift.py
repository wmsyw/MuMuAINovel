from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "organization_members_organization_id_fkey",
        "organization_members",
        type_="foreignkey",
    )
    op.alter_column(
        "organization_members",
        "organization_id",
        existing_type=sa.String(length=36),
        nullable=True,
        existing_comment="组织ID",
    )
    op.create_foreign_key(
        "organization_members_organization_id_fkey",
        "organization_members",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        op.f("ix_extraction_candidates_source_chapter_start_id"),
        "extraction_candidates",
        ["source_chapter_start_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extraction_candidates_source_chapter_end_id"),
        "extraction_candidates",
        ["source_chapter_end_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relationship_timeline_events_character_id"),
        "relationship_timeline_events",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relationship_timeline_events_organization_member_id"),
        "relationship_timeline_events",
        ["organization_member_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relationship_timeline_events_provenance_id"),
        "relationship_timeline_events",
        ["provenance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relationship_timeline_events_related_character_id"),
        "relationship_timeline_events",
        ["related_character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relationship_timeline_events_source_chapter_id"),
        "relationship_timeline_events",
        ["source_chapter_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_relationship_timeline_events_source_chapter_id"), table_name="relationship_timeline_events")
    op.drop_index(op.f("ix_relationship_timeline_events_related_character_id"), table_name="relationship_timeline_events")
    op.drop_index(op.f("ix_relationship_timeline_events_provenance_id"), table_name="relationship_timeline_events")
    op.drop_index(op.f("ix_relationship_timeline_events_organization_member_id"), table_name="relationship_timeline_events")
    op.drop_index(op.f("ix_relationship_timeline_events_character_id"), table_name="relationship_timeline_events")
    op.drop_index(op.f("ix_extraction_candidates_source_chapter_end_id"), table_name="extraction_candidates")
    op.drop_index(op.f("ix_extraction_candidates_source_chapter_start_id"), table_name="extraction_candidates")

    op.drop_constraint(
        "organization_members_organization_id_fkey",
        "organization_members",
        type_="foreignkey",
    )
    op.alter_column(
        "organization_members",
        "organization_id",
        existing_type=sa.String(length=36),
        nullable=False,
        existing_comment="组织ID",
    )
    op.create_foreign_key(
        "organization_members_organization_id_fkey",
        "organization_members",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
