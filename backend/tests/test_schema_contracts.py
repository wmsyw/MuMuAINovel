# pyright: reportUnknownMemberType=false, reportAny=false

from app.config import settings as app_settings
from app.database import Base


REQUIRED_EXTRACTION_TABLES = {
    "organization_entities",
    "entity_relationships",
    "extraction_runs",
    "extraction_candidates",
    "entity_aliases",
    "entity_provenance",
    "relationship_timeline_events",
    "world_setting_results",
}


def column_names(table_name: str) -> set[str]:
    return {column.name for column in Base.metadata.tables[table_name].columns}


def index_names(table_name: str) -> set[str]:
    return {index.name or "" for index in Base.metadata.tables[table_name].indexes}


def test_extraction_tables_are_registered_in_base_metadata() -> None:
    assert REQUIRED_EXTRACTION_TABLES.issubset(Base.metadata.tables.keys())


def test_character_model_no_longer_contains_organization_columns() -> None:
    assert {
        "is_organization",
        "organization_type",
        "organization_purpose",
        "organization_members",
    }.isdisjoint(column_names("characters"))


def test_organization_entity_absorbs_legacy_character_and_detail_fields() -> None:
    assert {
        "id",
        "project_id",
        "name",
        "normalized_name",
        "personality",
        "background",
        "status",
        "current_state",
        "avatar_url",
        "traits",
        "organization_type",
        "organization_purpose",
        "parent_org_id",
        "level",
        "power_level",
        "member_count",
        "location",
        "motto",
        "color",
        "legacy_character_id",
        "legacy_organization_id",
    }.issubset(column_names("organization_entities"))
    assert {"parent_org_id", "level", "power_level", "member_count", "location", "motto", "color"}.isdisjoint(
        column_names("organizations")
    )
    assert "organization_entity_id" in column_names("organization_members")
    assert Base.metadata.tables["organization_members"].columns["organization_entity_id"].nullable is False
    assert "idx_org_entities_project_name" in index_names("organization_entities")


def test_entity_relationships_support_typed_character_and_organization_endpoints() -> None:
    assert {
        "from_entity_type",
        "from_entity_id",
        "to_entity_type",
        "to_entity_id",
        "legacy_character_relationship_id",
        "relationship_name",
        "status",
    }.issubset(column_names("entity_relationships"))
    assert "idx_entity_relationships_from" in index_names("entity_relationships")
    assert "idx_entity_relationships_to" in index_names("entity_relationships")


def test_extraction_candidate_contract_uses_required_target_and_timeline_fields() -> None:
    assert {
        "run_id",
        "project_id",
        "user_id",
        "source_chapter_id",
        "source_chapter_start_id",
        "source_chapter_end_id",
        "candidate_type",
        "trigger_type",
        "source_hash",
        "provider",
        "model",
        "reasoning_intensity",
        "status",
        "confidence",
        "evidence_text",
        "source_start_offset",
        "source_end_offset",
        "source_chapter_number",
        "source_chapter_order",
        "canonical_target_type",
        "canonical_target_id",
        "valid_from_chapter_id",
        "valid_from_chapter_order",
        "valid_to_chapter_id",
        "valid_to_chapter_order",
        "story_time_label",
        "reviewed_at",
        "accepted_at",
        "supersedes_candidate_id",
        "rollback_of_candidate_id",
        "payload",
        "raw_payload",
    }.issubset(column_names("extraction_candidates"))
    assert "canonical_entity_type" not in column_names("extraction_candidates")
    assert "canonical_entity_id" not in column_names("extraction_candidates")
    assert "idx_extraction_candidates_canonical" in index_names("extraction_candidates")
    assert "idx_extraction_candidates_source_hash" in index_names("extraction_candidates")
    assert "idx_extraction_candidates_timeline" in index_names("extraction_candidates")


def test_provenance_timeline_and_world_result_contracts() -> None:
    assert {
        "entity_type",
        "entity_id",
        "source_type",
        "candidate_id",
        "run_id",
        "chapter_id",
        "claim_type",
        "claim_payload",
        "evidence_text",
        "source_start",
        "source_end",
        "confidence",
        "status",
    }.issubset(column_names("entity_provenance"))
    assert {
        "event_type",
        "event_status",
        "relationship_id",
        "organization_member_id",
        "organization_entity_id",
        "career_id",
        "source_chapter_id",
        "source_chapter_order",
        "valid_from_chapter_id",
        "valid_from_chapter_order",
        "valid_to_chapter_id",
        "valid_to_chapter_order",
        "story_time_label",
        "evidence_text",
        "provenance_id",
    }.issubset(column_names("relationship_timeline_events"))
    assert "chapter_number" not in column_names("relationship_timeline_events")
    assert {
        "project_id",
        "run_id",
        "status",
        "world_time_period",
        "world_location",
        "world_atmosphere",
        "world_rules",
        "provider",
        "model",
        "reasoning_intensity",
        "raw_result",
        "accepted_at",
        "supersedes_result_id",
    }.issubset(column_names("world_setting_results"))
    assert "world_time_period" in column_names("projects")
    assert "world_rules" in column_names("projects")


def test_settings_and_feature_flag_defaults() -> None:
    assert {
        "default_reasoning_intensity",
        "reasoning_overrides",
        "allow_ai_entity_generation",
    }.issubset(column_names("settings"))
    reasoning_column = Base.metadata.tables["settings"].columns["reasoning_overrides"]
    assert reasoning_column.nullable is True
    assert app_settings.default_reasoning_intensity == "auto"
    assert app_settings.reasoning_overrides == "{}"
    assert app_settings.allow_ai_entity_generation is False
    assert app_settings.EXTRACTION_PIPELINE_ENABLED is False
