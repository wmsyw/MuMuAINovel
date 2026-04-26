# pyright: reportUnknownVariableType=false

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_MIGRATION = BACKEND_ROOT / "alembic/postgres/versions/20260426_1200_b7c8d9e0f1a2_extraction_graph_org_split.py"
SQLITE_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260426_1202_c8d9e0f1a2b3_extraction_graph_org_split.py"

REQUIRED_DECLARATIONS = [
    "organization_entities",
    "entity_relationships",
    "extraction_runs",
    "extraction_candidates",
    "entity_aliases",
    "entity_provenance",
    "relationship_timeline_events",
    "world_setting_results",
    "organization_entity_id",
    "canonical_target_type",
    "valid_from_chapter_id",
    "valid_to_chapter_id",
    "source_start_offset",
    "source_end_offset",
    "supersedes_candidate_id",
    "rollback_of_candidate_id",
    "default_reasoning_intensity",
    "reasoning_overrides",
    "allow_ai_entity_generation",
    "idx_org_entities_project_name",
    "idx_entity_relationships_from",
    "idx_extraction_runs_project_content",
    "idx_extraction_candidates_source_hash",
    "idx_extraction_candidates_timeline",
    "idx_extraction_candidates_project_type_status",
    "idx_entity_aliases_lookup",
    "idx_entity_provenance_project_claim",
    "idx_relationship_timeline_project_position",
    "idx_world_setting_results_project_status",
]


def test_extraction_migrations_exist_in_both_alembic_trees() -> None:
    assert POSTGRES_MIGRATION.exists()
    assert SQLITE_MIGRATION.exists()


def test_postgres_and_sqlite_migrations_declare_same_required_schema_intent() -> None:
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


def test_both_migrations_preserve_legacy_organization_data_path() -> None:
    for migration_path in (POSTGRES_MIGRATION, SQLITE_MIGRATION):
        source = migration_path.read_text(encoding="utf-8")
        assert "LEFT JOIN organizations o ON o.character_id = c.id" in source
        assert "FROM characters c" in source
        assert "INSERT INTO organization_entities" in source
        assert "UPDATE organizations SET organization_entity_id" in source
        assert "UPDATE organization_members SET organization_entity_id" in source
        assert "alter_column" in source and "organization_entity_id" in source and "nullable=False" in source
        assert "DELETE FROM characters WHERE is_organization" in source
        assert "drop_column" in source and "is_organization" in source
        assert "drop_column" in source and "organization_type" in source
        assert "drop_column" in source and "organization_purpose" in source
        assert "drop_column" in source and "organization_members" in source
        assert "INSERT INTO entity_relationships" in source


def test_sqlite_migration_uses_batch_mode_for_existing_table_changes() -> None:
    source = SQLITE_MIGRATION.read_text(encoding="utf-8")
    assert "batch_alter_table('settings'" in source
    assert "batch_alter_table('organizations'" in source
    assert "batch_alter_table('organization_members'" in source
    assert "batch_alter_table('characters'" in source
