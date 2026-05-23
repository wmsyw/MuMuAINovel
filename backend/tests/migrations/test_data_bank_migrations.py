from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

from app.database import Base


BACKEND_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_MIGRATION = BACKEND_ROOT / "alembic/postgres/versions/20260522_1500_b1c2d3e4f5a6_add_data_bank.py"
SQLITE_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260522_1502_c1d2e3f4a5b6_add_data_bank.py"

REQUIRED_DECLARATIONS = [
    "data_bank_items",
    "data_bank_chunks",
    "project_id",
    "user_id",
    "source_type",
    "snippet",
    "upload",
    "filename",
    "content_hash",
    "text_content",
    "chunk_count",
    "chunk_index",
    "char_start",
    "char_end",
    "metadata",
    "ck_data_bank_items_source_type",
    "idx_data_bank_items_project_user_created",
    "idx_data_bank_chunks_project_user_item",
    "idx_data_bank_chunks_item_index",
    "projects.id",
    "ondelete=\"CASCADE\"",
]


def test_data_bank_migrations_exist_in_both_alembic_trees() -> None:
    assert POSTGRES_MIGRATION.exists()
    assert SQLITE_MIGRATION.exists()


def test_data_bank_migrations_declare_same_schema_intent() -> None:
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


def test_data_bank_migrations_extend_current_heads() -> None:
    assert "down_revision: Union[str, None] = \"a9b0c1d2e3f4\"" in POSTGRES_MIGRATION.read_text(encoding="utf-8")
    assert "down_revision: Union[str, None] = \"b0c1d2e3f4a5\"" in SQLITE_MIGRATION.read_text(encoding="utf-8")


def test_data_bank_migrations_do_not_touch_canon_or_remote_ingestion() -> None:
    combined_source = POSTGRES_MIGRATION.read_text(encoding="utf-8") + SQLITE_MIGRATION.read_text(encoding="utf-8")

    assert "characters" not in combined_source
    assert "world_setting_results" not in combined_source
    assert "source_url" not in combined_source
    assert "remote_url" not in combined_source


def test_data_bank_models_registered_in_metadata() -> None:
    assert "data_bank_items" in Base.metadata.tables
    assert "data_bank_chunks" in Base.metadata.tables
    items = Base.metadata.tables["data_bank_items"]
    chunks = Base.metadata.tables["data_bank_chunks"]
    assert {
        "id",
        "project_id",
        "user_id",
        "title",
        "source_type",
        "filename",
        "content_type",
        "content_hash",
        "text_content",
        "chunk_count",
        "metadata",
        "created_at",
        "updated_at",
    }.issubset(set(items.c.keys()))
    assert {
        "id",
        "item_id",
        "project_id",
        "user_id",
        "chunk_index",
        "content",
        "char_start",
        "char_end",
        "content_hash",
        "metadata",
        "created_at",
    }.issubset(set(chunks.c.keys()))
    item_targets = {foreign_key.target_fullname for foreign_key in items.foreign_keys}
    chunk_targets = {foreign_key.target_fullname for foreign_key in chunks.foreign_keys}
    assert item_targets == {"projects.id"}
    assert chunk_targets == {"projects.id", "data_bank_items.id"}
