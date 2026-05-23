from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from pathlib import Path

from app.database import Base


BACKEND_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_MIGRATION = BACKEND_ROOT / "alembic/postgres/versions/20260522_1200_c5e6f7a8b9c0_add_creative_sessions.py"
SQLITE_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260522_1202_d6e7f8a9b0c1_add_creative_sessions.py"

REQUIRED_DECLARATIONS = [
    "creative_sessions",
    "creative_session_messages",
    "project_id",
    "user_id",
    "session_id",
    "role",
    "content",
    "position",
    "metadata",
    "ck_creative_sessions_status",
    "ck_creative_session_messages_role",
    "idx_creative_sessions_project_user_updated",
    "idx_creative_session_messages_session_position",
    "idx_creative_session_messages_project_user_created",
]


def test_creative_session_migrations_exist_in_both_alembic_trees() -> None:
    assert POSTGRES_MIGRATION.exists()
    assert SQLITE_MIGRATION.exists()


def test_creative_session_migrations_declare_same_schema_intent() -> None:
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


def test_creative_session_migrations_extend_current_heads() -> None:
    assert "down_revision: Union[str, None] = \"b8c9d0e1f2a3\"" in POSTGRES_MIGRATION.read_text(encoding="utf-8")
    assert "down_revision: Union[str, None] = \"e4f5a6b7c8d9\"" in SQLITE_MIGRATION.read_text(encoding="utf-8")


def test_creative_session_models_registered_in_metadata() -> None:
    assert "creative_sessions" in Base.metadata.tables
    assert "creative_session_messages" in Base.metadata.tables
