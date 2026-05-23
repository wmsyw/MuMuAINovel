from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

from app.database import Base


BACKEND_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_MIGRATION = BACKEND_ROOT / "alembic/postgres/versions/20260522_1400_a9b0c1d2e3f4_add_lorebook_entries.py"
SQLITE_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260522_1402_b0c1d2e3f4a5_add_lorebook_entries.py"

REQUIRED_DECLARATIONS = [
    "lorebook_entries",
    "project_id",
    "user_id",
    "title",
    "content",
    "activation_keys",
    "priority",
    "enabled",
    "source_type",
    "metadata",
    "idx_lorebook_entries_project_user_priority",
    "idx_lorebook_entries_project_enabled",
    "projects.id",
    "ondelete=\"CASCADE\"",
]


def test_lorebook_migrations_exist_in_both_alembic_trees() -> None:
    assert POSTGRES_MIGRATION.exists()
    assert SQLITE_MIGRATION.exists()


def test_lorebook_migrations_declare_same_schema_intent() -> None:
    postgres_source = POSTGRES_MIGRATION.read_text(encoding="utf-8")
    sqlite_source = SQLITE_MIGRATION.read_text(encoding="utf-8")
    missing = {
        declaration: {
            "postgres": declaration in postgres_source,
            "sqlite": declaration in sqlite_source,
        }
        for declaration in REQUIRED_DECLARATIONS
        if declaration not in postgres_source or declaration not in sqlite_source
    }
    assert missing == {}


def test_lorebook_migrations_extend_current_heads() -> None:
    assert "down_revision: Union[str, None] = \"e7f8a9b0c1d2\"" in POSTGRES_MIGRATION.read_text(encoding="utf-8")
    assert "down_revision: Union[str, None] = \"f8a9b0c1d2e3\"" in SQLITE_MIGRATION.read_text(encoding="utf-8")


def test_lorebook_migrations_do_not_touch_world_setting_results() -> None:
    combined_source = POSTGRES_MIGRATION.read_text(encoding="utf-8") + SQLITE_MIGRATION.read_text(encoding="utf-8")

    assert "world_setting_results" not in combined_source
    assert "WorldSettingResult" not in combined_source


def test_lorebook_model_registered_in_metadata_as_independent_project_table() -> None:
    assert "lorebook_entries" in Base.metadata.tables
    lorebook_entries = Base.metadata.tables["lorebook_entries"]
    assert {
        "id",
        "project_id",
        "user_id",
        "title",
        "content",
        "activation_keys",
        "priority",
        "enabled",
        "source_type",
        "metadata",
        "created_at",
        "updated_at",
    }.issubset(set(lorebook_entries.c.keys()))
    foreign_key_targets = {foreign_key.target_fullname for foreign_key in lorebook_entries.foreign_keys}
    assert foreign_key_targets == {"projects.id"}
