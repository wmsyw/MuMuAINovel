"""Migrate legacy provider and SMTP defaults.

This revision intentionally records the rows it changes so a downgrade restores
only those legacy values, without rewriting rows that were already canonical.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5e6f708192a3"
down_revision: Union[str, None] = "3c4d5e6f7081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKUP_TABLE_NAME = "_legacy_provider_defaults_backup"


def _cover_provider(base_url: str | None, model: str | None) -> str:
    """Resolve the supported cover provider represented by a legacy row."""
    normalized_url = (base_url or "").strip().lower()
    normalized_model = (model or "").strip().lower()
    if "v1beta" in normalized_url or normalized_model.startswith("gemini"):
        return "gemini"
    if "api.openai.com" in normalized_url or normalized_model.startswith("gpt-image-"):
        return "openai"
    return "grok"


def _tables() -> tuple[sa.TableClause, sa.TableClause]:
    settings = sa.table(
        "settings",
        sa.column("id", sa.String(length=100)),
        sa.column("api_provider", sa.String(length=50)),
        sa.column("cover_api_provider", sa.String(length=50)),
        sa.column("cover_api_base_url", sa.String(length=500)),
        sa.column("cover_image_model", sa.String(length=100)),
        sa.column("smtp_from_name", sa.String(length=255)),
    )
    backup = sa.table(
        BACKUP_TABLE_NAME,
        sa.column("table_name", sa.String(length=50)),
        sa.column("row_id", sa.String(length=100)),
        sa.column("field_name", sa.String(length=50)),
        sa.column("legacy_value", sa.Text()),
    )
    return settings, backup


def upgrade() -> None:
    op.create_table(
        BACKUP_TABLE_NAME,
        sa.Column("table_name", sa.String(length=50), nullable=False),
        sa.Column("row_id", sa.String(length=100), nullable=False),
        sa.Column("field_name", sa.String(length=50), nullable=False),
        sa.Column("legacy_value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("table_name", "row_id", "field_name"),
    )

    bind = op.get_bind()
    settings, backup = _tables()
    backup_rows: list[dict[str, str]] = []

    text_provider_rows = bind.execute(
        sa.select(settings.c.id, settings.c.api_provider).where(
            sa.func.lower(settings.c.api_provider) == "mumu"
        )
    ).mappings().all()
    for row in text_provider_rows:
        backup_rows.append({
            "table_name": "settings",
            "row_id": row["id"],
            "field_name": "api_provider",
            "legacy_value": row["api_provider"],
        })

    cover_rows = bind.execute(
        sa.select(
            settings.c.id,
            settings.c.cover_api_provider,
            settings.c.cover_api_base_url,
            settings.c.cover_image_model,
        ).where(sa.func.lower(settings.c.cover_api_provider) == "mumu")
    ).mappings().all()
    cover_updates: list[tuple[str, str]] = []
    for row in cover_rows:
        backup_rows.append({
            "table_name": "settings",
            "row_id": row["id"],
            "field_name": "cover_api_provider",
            "legacy_value": row["cover_api_provider"],
        })
        cover_updates.append((row["id"], _cover_provider(row["cover_api_base_url"], row["cover_image_model"])))

    smtp_rows = bind.execute(
        sa.select(settings.c.id, settings.c.smtp_from_name).where(
            settings.c.smtp_from_name == "MuMuAINovel"
        )
    ).mappings().all()
    for row in smtp_rows:
        backup_rows.append({
            "table_name": "settings",
            "row_id": row["id"],
            "field_name": "smtp_from_name",
            "legacy_value": row["smtp_from_name"],
        })

    if backup_rows:
        bind.execute(backup.insert(), backup_rows)

    for row in text_provider_rows:
        bind.execute(
            settings.update().where(settings.c.id == row["id"]).values(api_provider="openai")
        )
    for row_id, provider in cover_updates:
        bind.execute(
            settings.update().where(settings.c.id == row_id).values(cover_api_provider=provider)
        )
    for row in smtp_rows:
        bind.execute(
            settings.update().where(settings.c.id == row["id"]).values(smtp_from_name="AI Novel Studio")
        )

    op.alter_column(
        "settings",
        "smtp_from_name",
        existing_type=sa.String(length=255),
        existing_server_default=sa.text("'MuMuAINovel'"),
        server_default=sa.text("'AI Novel Studio'"),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    settings, backup = _tables()
    backup_rows = bind.execute(
        sa.select(
            backup.c.table_name,
            backup.c.row_id,
            backup.c.field_name,
            backup.c.legacy_value,
        )
    ).mappings().all()

    for row in backup_rows:
        if row["table_name"] != "settings":
            continue
        if row["field_name"] not in {"api_provider", "cover_api_provider", "smtp_from_name"}:
            continue
        bind.execute(
            settings.update()
            .where(settings.c.id == row["row_id"])
            .values({row["field_name"]: row["legacy_value"]})
        )

    op.alter_column(
        "settings",
        "smtp_from_name",
        existing_type=sa.String(length=255),
        existing_server_default=sa.text("'AI Novel Studio'"),
        server_default=sa.text("'MuMuAINovel'"),
        existing_nullable=False,
    )
    op.drop_table(BACKUP_TABLE_NAME)
