import ast
from pathlib import Path

from app.schemas.settings import ReasoningCapabilityResponse, SettingsCreate, SettingsResponse
from app.services.ai_capabilities import get_reasoning_registry_metadata


BACKEND_ROOT = Path(__file__).resolve().parents[1]
LIVE_APP_FILES = [
    BACKEND_ROOT / "app/api/chapters.py",
    BACKEND_ROOT / "app/api/outlines.py",
    BACKEND_ROOT / "app/api/relationships.py",
    BACKEND_ROOT / "app/api/wizard_stream.py",
    BACKEND_ROOT / "app/services/auto_character_service.py",
    BACKEND_ROOT / "app/services/auto_organization_service.py",
    BACKEND_ROOT / "app/services/book_import_service.py",
    BACKEND_ROOT / "app/services/chapter_context_service.py",
    BACKEND_ROOT / "app/services/character_state_update_service.py",
    BACKEND_ROOT / "app/services/import_export_service.py",
    BACKEND_ROOT / "app/utils/data_consistency.py",
]
REMOVED_CHARACTER_ORG_FIELDS = {"is_organization", "organization_type", "organization_purpose"}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_live_legacy_surfaces_do_not_dereference_removed_character_org_attributes() -> None:
    offenders: list[str] = []
    for file_path in LIVE_APP_FILES:
        for node in ast.walk(_tree(file_path)):
            if isinstance(node, ast.Attribute) and node.attr == "is_organization":
                offenders.append(f"{file_path.relative_to(BACKEND_ROOT)}:{node.lineno}: .{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Character":
                for keyword in node.keywords:
                    if keyword.arg in REMOVED_CHARACTER_ORG_FIELDS:
                        offenders.append(f"{file_path.relative_to(BACKEND_ROOT)}:{node.lineno}: Character({keyword.arg}=...)")

    assert offenders == []


def test_context_export_import_paths_use_organization_entities_and_membership_bridge() -> None:
    import_export_source = (BACKEND_ROOT / "app/services/import_export_service.py").read_text(encoding="utf-8")
    chapter_context_source = (BACKEND_ROOT / "app/services/chapter_context_service.py").read_text(encoding="utf-8")
    chapters_source = (BACKEND_ROOT / "app/api/chapters.py").read_text(encoding="utf-8")

    assert "OrganizationEntity" in import_export_source
    assert "create_organization_entity_from_payload" in import_export_source
    assert "organization_entity_id" in import_export_source
    assert "OrganizationEntity" in chapter_context_source
    assert "organization_entity_id" in chapter_context_source
    assert "OrganizationEntity" in chapters_source
    assert "organization_entity_id" in chapters_source


def test_provider_native_metadata_stays_read_only_and_out_of_settings_state() -> None:
    settings_fields = set(SettingsCreate.model_fields) | set(SettingsResponse.model_fields)
    assert "provider_native" not in settings_fields
    assert "provider_payload_mappings" not in settings_fields

    capability_fields = set(ReasoningCapabilityResponse.model_fields)
    assert "provider_metadata" in capability_fields
    assert "provider_native" not in capability_fields
    assert "provider_payload_mappings" not in capability_fields

    metadata = get_reasoning_registry_metadata()
    assert metadata["capabilities"]
    for capability in metadata["capabilities"]:
        assert "provider_native" not in capability
        assert "provider_payload_mappings" not in capability
        assert capability["provider_metadata"]["read_only"] is True
        assert capability["provider_metadata"]["native_field"]
