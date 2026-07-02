from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table(
        "organizations",
        schema=None,
        naming_convention=FK_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint("fk_organizations_character_id_characters", type_="foreignkey")

    with op.batch_alter_table(
        "organization_members",
        schema=None,
        naming_convention=FK_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint("fk_organization_members_organization_id_organizations", type_="foreignkey")
        batch_op.alter_column(
            "organization_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.create_foreign_key(
            "fk_organization_members_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("extraction_candidates", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_extraction_candidates_source_chapter_start_id"),
            ["source_chapter_start_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_extraction_candidates_source_chapter_end_id"),
            ["source_chapter_end_id"],
            unique=False,
        )

    with op.batch_alter_table("relationship_timeline_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_relationship_timeline_events_character_id"), ["character_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_relationship_timeline_events_organization_member_id"),
            ["organization_member_id"],
            unique=False,
        )
        batch_op.create_index(batch_op.f("ix_relationship_timeline_events_provenance_id"), ["provenance_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_relationship_timeline_events_related_character_id"),
            ["related_character_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_relationship_timeline_events_source_chapter_id"),
            ["source_chapter_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("relationship_timeline_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_relationship_timeline_events_source_chapter_id"))
        batch_op.drop_index(batch_op.f("ix_relationship_timeline_events_related_character_id"))
        batch_op.drop_index(batch_op.f("ix_relationship_timeline_events_provenance_id"))
        batch_op.drop_index(batch_op.f("ix_relationship_timeline_events_organization_member_id"))
        batch_op.drop_index(batch_op.f("ix_relationship_timeline_events_character_id"))

    with op.batch_alter_table("extraction_candidates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_extraction_candidates_source_chapter_end_id"))
        batch_op.drop_index(batch_op.f("ix_extraction_candidates_source_chapter_start_id"))

    with op.batch_alter_table(
        "organization_members",
        schema=None,
        naming_convention=FK_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint("fk_organization_members_organization_id", type_="foreignkey")
        batch_op.alter_column(
            "organization_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_organization_members_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table(
        "organizations",
        schema=None,
        naming_convention=FK_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.create_foreign_key(
            "fk_organizations_character_id",
            "characters",
            ["character_id"],
            ["id"],
            ondelete="CASCADE",
        )
