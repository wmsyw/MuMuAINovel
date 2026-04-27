# pyright: reportUnknownMemberType=false, reportAny=false, reportUnknownVariableType=false

import importlib.util
from pathlib import Path

import sqlalchemy as sa
import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.database import Base


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SQLITE_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260426_1202_c8d9e0f1a2b3_extraction_graph_org_split.py"
SQLITE_GOLDFINGER_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260427_0902_e0f1a2b3c4d5_add_goldfinger_schema.py"
SQLITE_RELATIONSHIP_BACKFILL_MIGRATION = BACKEND_ROOT / "alembic/sqlite/versions/20260427_1302_f1a2b3c4d5e7_backfill_character_relationships_to_entity.py"


def load_sqlite_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def create_minimal_legacy_schema(connection: sa.Connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "settings",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(50), nullable=False),
    )
    sa.Table(
        "projects",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("world_time_period", sa.Text()),
        sa.Column("world_location", sa.Text()),
        sa.Column("world_atmosphere", sa.Text()),
        sa.Column("world_rules", sa.Text()),
    )
    sa.Table(
        "characters",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("age", sa.String(50)),
        sa.Column("gender", sa.String(50)),
        sa.Column("is_organization", sa.Boolean()),
        sa.Column("personality", sa.Text()),
        sa.Column("background", sa.Text()),
        sa.Column("status", sa.String(20)),
        sa.Column("current_state", sa.Text()),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("traits", sa.Text()),
        sa.Column("organization_type", sa.String(100)),
        sa.Column("organization_purpose", sa.String(500)),
        sa.Column("organization_members", sa.Text()),
    )
    sa.Table(
        "organizations",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("parent_org_id", sa.String(36)),
        sa.Column("level", sa.Integer()),
        sa.Column("power_level", sa.Integer()),
        sa.Column("member_count", sa.Integer()),
        sa.Column("location", sa.Text()),
        sa.Column("motto", sa.String(200)),
        sa.Column("color", sa.String(100)),
    )
    sa.Table(
        "organization_members",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=False),
        sa.Column("position", sa.String(100), nullable=False),
    )
    sa.Table("chapters", metadata, sa.Column("id", sa.String(36), primary_key=True))
    sa.Table("careers", metadata, sa.Column("id", sa.String(36), primary_key=True))
    sa.Table("users", metadata, sa.Column("user_id", sa.String(100), primary_key=True))
    sa.Table("relationship_types", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table(
        "character_relationships",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("character_from_id", sa.String(36), nullable=False),
        sa.Column("character_to_id", sa.String(36), nullable=False),
        sa.Column("relationship_type_id", sa.Integer()),
        sa.Column("relationship_name", sa.String(100)),
        sa.Column("intimacy_level", sa.Integer()),
        sa.Column("status", sa.String(20)),
        sa.Column("description", sa.Text()),
        sa.Column("started_at", sa.String(100)),
        sa.Column("ended_at", sa.String(100)),
        sa.Column("source", sa.String(20)),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    metadata.create_all(connection)

    connection.execute(sa.text("INSERT INTO settings (id, user_id) VALUES ('settings-1', 'user-1')"))
    connection.execute(sa.text("INSERT INTO projects (id, user_id, title) VALUES ('project-1', 'user-1', '测试项目')"))
    connection.execute(sa.text(
        """
        INSERT INTO characters (
            id, project_id, name, is_organization, personality, background, status,
            current_state, avatar_url, traits, organization_type,
            organization_purpose, organization_members
        ) VALUES (
            'char-org-1', 'project-1', '青岚阁', 1, '戒律森严', '守护北境的宗门',
            'active', '声望上升', '/avatars/qinglan.png', '["宗门"]', '宗门',
            '守护封印', '["林青岚"]'
        )
        """
    ))
    connection.execute(sa.text(
        """
        INSERT INTO characters (id, project_id, name, is_organization, personality, background, status)
        VALUES ('char-1', 'project-1', '林青岚', 0, '冷静', '北境剑修', 'active')
        """
    ))
    connection.execute(sa.text(
        """
        INSERT INTO organizations (
            id, character_id, project_id, parent_org_id, level, power_level,
            member_count, location, motto, color
        ) VALUES (
            'org-1', 'char-org-1', 'project-1', NULL, 2, 88,
            300, '北境雪山', '护道守心', '青色'
        )
        """
    ))
    connection.execute(sa.text(
        """
        INSERT INTO organization_members (id, organization_id, character_id, position)
        VALUES ('member-1', 'org-1', 'char-1', '阁主')
        """
    ))
    connection.execute(sa.text(
        """
        INSERT INTO character_relationships (
            id, project_id, character_from_id, character_to_id, relationship_type_id,
            relationship_name, intimacy_level, status, description, started_at, ended_at, source
        ) VALUES (
            'rel-1', 'project-1', 'char-org-1', 'char-1', NULL,
            '庇护', 80, 'active', '青岚阁庇护林青岚', '第一章', NULL, 'manual'
        )
        """
    ))


def upgrade_legacy_schema(connection: sa.Connection) -> None:
    context = MigrationContext.configure(connection)
    for path, module_name in (
        (SQLITE_MIGRATION, "sqlite_extraction_graph_org_split"),
        (SQLITE_GOLDFINGER_MIGRATION, "sqlite_goldfinger_schema"),
        (SQLITE_RELATIONSHIP_BACKFILL_MIGRATION, "sqlite_relationship_backfill"),
    ):
        migration = load_sqlite_migration(path, module_name)
        migration.op = Operations(context)
        migration.upgrade()


def test_fresh_database_has_extraction_graph_schema() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        inspector = sa.inspect(connection)
        assert {
            "organization_entities",
            "entity_relationships",
            "extraction_runs",
            "extraction_candidates",
            "entity_aliases",
            "entity_provenance",
            "relationship_timeline_events",
            "world_setting_results",
            "goldfingers",
            "goldfinger_history_events",
        }.issubset(inspector.get_table_names())
        assert "is_organization" not in {column["name"] for column in inspector.get_columns("characters")}
        assert "canonical_target_type" in {column["name"] for column in inspector.get_columns("extraction_candidates")}
        assert "review_required_reason" in {column["name"] for column in inspector.get_columns("extraction_candidates")}
        assert "canonical_entity_type" not in {column["name"] for column in inspector.get_columns("extraction_candidates")}


def test_goldfinger_status_rejects_invalid_values() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        goldfingers = Base.metadata.tables["goldfingers"]

        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.insert(goldfingers).values(
                id="gf-invalid-status",
                project_id="project-1",
                name="错误状态系统",
                normalized_name="错误状态系统",
                status="super_active",
            ))

        count = connection.execute(sa.select(sa.func.count()).select_from(goldfingers)).scalar_one()
        assert count == 0


def test_org_split_migration_preserves_data() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_minimal_legacy_schema(connection)
        upgrade_legacy_schema(connection)

        inspector = sa.inspect(connection)
        character_columns = {column["name"] for column in inspector.get_columns("characters")}
        assert {"is_organization", "organization_type", "organization_purpose", "organization_members"}.isdisjoint(character_columns)
        organization_columns = {column["name"] for column in inspector.get_columns("organizations")}
        assert {"parent_org_id", "level", "power_level", "member_count", "location", "motto", "color"}.isdisjoint(organization_columns)
        organization_member_columns = {column["name"]: column for column in inspector.get_columns("organization_members")}
        assert organization_member_columns["organization_entity_id"]["nullable"] is False

        remaining_characters = connection.execute(sa.text("SELECT id, name FROM characters ORDER BY id")).mappings().all()
        assert [row["id"] for row in remaining_characters] == ["char-1"]

        org_entity = connection.execute(sa.text(
            """
            SELECT id, project_id, name, normalized_name, personality, background, status,
                   current_state, avatar_url, traits, organization_type, organization_purpose,
                   legacy_character_id, legacy_organization_id, level, power_level,
                   member_count, location, motto, color, source
            FROM organization_entities
            """
        )).mappings().one()
        assert org_entity["project_id"] == "project-1"
        assert org_entity["name"] == "青岚阁"
        assert org_entity["personality"] == "戒律森严"
        assert org_entity["background"] == "守护北境的宗门"
        assert org_entity["current_state"] == "声望上升"
        assert org_entity["avatar_url"] == "/avatars/qinglan.png"
        assert org_entity["traits"] == '["宗门"]'
        assert org_entity["organization_type"] == "宗门"
        assert org_entity["organization_purpose"] == "守护封印"
        assert org_entity["legacy_character_id"] == "char-org-1"
        assert org_entity["legacy_organization_id"] == "org-1"
        assert org_entity["level"] == 2
        assert org_entity["power_level"] == 88
        assert org_entity["member_count"] == 300
        assert org_entity["location"] == "北境雪山"
        assert org_entity["motto"] == "护道守心"
        assert org_entity["color"] == "青色"
        assert org_entity["source"] == "legacy"

        linked_org = connection.execute(sa.text(
            "SELECT organization_entity_id FROM organizations WHERE id = 'org-1'"
        )).scalar_one()
        linked_member = connection.execute(sa.text(
            "SELECT organization_entity_id FROM organization_members WHERE id = 'member-1'"
        )).scalar_one()
        assert linked_org == org_entity["id"]
        assert linked_member == org_entity["id"]


def test_entity_relationship_migration_preserves_old_relationship_endpoints() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_minimal_legacy_schema(connection)
        upgrade_legacy_schema(connection)

        org_entity_id = connection.execute(sa.text("SELECT id FROM organization_entities")).scalar_one()
        relationship = connection.execute(sa.text(
            """
            SELECT from_entity_type, from_entity_id, to_entity_type, to_entity_id,
                   relationship_name, status, legacy_character_relationship_id
            FROM entity_relationships
            """
        )).mappings().one()
        assert relationship["from_entity_type"] == "organization"
        assert relationship["from_entity_id"] == org_entity_id
        assert relationship["to_entity_type"] == "character"
        assert relationship["to_entity_id"] == "char-1"
        assert relationship["relationship_name"] == "庇护"
        assert relationship["status"] == "active"
        assert relationship["legacy_character_relationship_id"] == "rel-1"


def test_relationship_backfill_migration_copies_post_upgrade_legacy_character_edges() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_minimal_legacy_schema(connection)
        # Run only the schema migrations first, then insert a late legacy row to
        # verify the Task 5 data-only backfill covers already-upgraded systems.
        for path, module_name in (
            (SQLITE_MIGRATION, "sqlite_extraction_graph_org_split_late"),
            (SQLITE_GOLDFINGER_MIGRATION, "sqlite_goldfinger_schema_late"),
        ):
            migration = load_sqlite_migration(path, module_name)
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()

        connection.execute(sa.text(
            """
            INSERT INTO character_relationships (
                id, project_id, character_from_id, character_to_id, relationship_type_id,
                relationship_name, intimacy_level, status, description, started_at, ended_at, source
            ) VALUES (
                'rel-late', 'project-1', 'char-1', 'char-1', NULL,
                '自省', 50, 'active', '后续旧路径写入', '第二章', NULL, 'manual'
            )
            """
        ))

        migration = load_sqlite_migration(SQLITE_RELATIONSHIP_BACKFILL_MIGRATION, "sqlite_relationship_backfill_late")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        relationship = connection.execute(sa.text(
            """
            SELECT from_entity_type, from_entity_id, to_entity_type, to_entity_id,
                   relationship_name, legacy_character_relationship_id
            FROM entity_relationships
            WHERE legacy_character_relationship_id = 'rel-late'
            """
        )).mappings().one()
        assert relationship["from_entity_type"] == "character"
        assert relationship["from_entity_id"] == "char-1"
        assert relationship["to_entity_type"] == "character"
        assert relationship["to_entity_id"] == "char-1"
        assert relationship["relationship_name"] == "自省"


def test_settings_columns_are_added_by_migration() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_minimal_legacy_schema(connection)
        upgrade_legacy_schema(connection)
        settings_columns = {column["name"]: column for column in sa.inspect(connection).get_columns("settings")}
        assert settings_columns["default_reasoning_intensity"]["nullable"] is False
        assert settings_columns["reasoning_overrides"]["nullable"] is True
        assert settings_columns["allow_ai_entity_generation"]["nullable"] is False


def test_goldfinger_migration_adds_tables_review_reason_and_status_constraint() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        create_minimal_legacy_schema(connection)
        upgrade_legacy_schema(connection)
        inspector = sa.inspect(connection)

        assert {"goldfingers", "goldfinger_history_events"}.issubset(inspector.get_table_names())
        goldfinger_columns = {column["name"] for column in inspector.get_columns("goldfingers")}
        assert {
            "id",
            "project_id",
            "name",
            "normalized_name",
            "owner_character_id",
            "owner_character_name",
            "type",
            "status",
            "summary",
            "rules",
            "tasks",
            "rewards",
            "limits",
            "trigger_conditions",
            "cooldown",
            "aliases",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "source",
            "confidence",
            "last_source_chapter_id",
        }.issubset(goldfinger_columns)
        history_columns = {column["name"] for column in inspector.get_columns("goldfinger_history_events")}
        assert {
            "goldfinger_id",
            "project_id",
            "chapter_id",
            "event_type",
            "old_value",
            "new_value",
            "evidence_excerpt",
            "confidence",
            "source_type",
            "created_at",
        }.issubset(history_columns)
        assert "review_required_reason" in {column["name"] for column in inspector.get_columns("extraction_candidates")}

        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text(
                """
                INSERT INTO goldfingers (id, project_id, name, normalized_name, status)
                VALUES ('gf-invalid', 'project-1', '错误状态系统', '错误状态系统', 'super_active')
                """
            ))
