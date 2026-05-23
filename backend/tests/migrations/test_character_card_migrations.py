from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

from app.database import Base


BACKEND_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_MIGRATION = BACKEND_ROOT / "alembic/postgres/versions/20260522_1300_e7f8a9b0c1d2_add_character_card_fields.py"
SQLITE_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260522_1302_f8a9b0c1d2e3_add_character_card_fields.py"

REQUIRED_DECLARATIONS = [
    "characters",
    "writing_notes",
    "speech_patterns",
    "motivations",
    "arc_summary",
    "card_version",
    "server_default=\"1\"",
]


def test_character_card_migrations_exist_in_both_alembic_trees() -> None:
    assert POSTGRES_MIGRATION.exists()
    assert SQLITE_MIGRATION.exists()


def test_character_card_migrations_declare_same_schema_intent() -> None:
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


def test_character_card_migrations_extend_current_heads() -> None:
    assert "down_revision: Union[str, None] = \"c5e6f7a8b9c0\"" in POSTGRES_MIGRATION.read_text(encoding="utf-8")
    assert "down_revision: Union[str, None] = \"d6e7f8a9b0c1\"" in SQLITE_MIGRATION.read_text(encoding="utf-8")


def test_character_card_model_columns_registered_in_metadata() -> None:
    characters = Base.metadata.tables["characters"]
    for column_name in ["writing_notes", "speech_patterns", "motivations", "arc_summary", "card_version"]:
        assert column_name in characters.c
