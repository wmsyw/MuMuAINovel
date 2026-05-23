from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnnecessaryIsInstance=false, reportUnreachable=false, reportUnusedCallResult=false

import json
from pathlib import Path
from typing import Any


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "novel_extraction_golden.json"
WORKFLOW_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "workflow_provenance_golden.json"

REQUIRED_EXPECTED_CATEGORIES = {
    "characters",
    "organization_affiliations",
    "profession_changes",
    "relationships",
    "world_facts",
    "ambiguous_duplicate_names",
    "contradictory_evidence",
}


def load_golden_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)

    validate_golden_fixture(fixture)
    return fixture


def load_workflow_fixture(path: Path = WORKFLOW_FIXTURE_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)

    validate_workflow_fixture(fixture)
    return fixture


def validate_golden_fixture(fixture: dict[str, Any]) -> None:
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")

    chapters = fixture.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("chapters must be a non-empty list")

    chapters_by_number = _index_chapters(chapters)
    expected = fixture.get("expected")
    if not isinstance(expected, dict):
        raise ValueError("expected must be an object")

    missing_categories = REQUIRED_EXPECTED_CATEGORIES - expected.keys()
    if missing_categories:
        raise ValueError(f"expected missing categories: {sorted(missing_categories)}")

    for category in REQUIRED_EXPECTED_CATEGORIES:
        assertions = expected.get(category)
        if not isinstance(assertions, list) or not assertions:
            raise ValueError(f"expected.{category} must be a non-empty list")
        for index, assertion in enumerate(assertions):
            _validate_expected_assertion(
                assertion,
                chapters_by_number,
                path=f"expected.{category}[{index}]",
            )


def validate_workflow_fixture(fixture: dict[str, Any]) -> None:
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")

    fixture_id = fixture.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id:
        raise ValueError("fixture_id is required")

    required_sections = {
        "user",
        "project",
        "character",
        "lore_entry",
        "prompt_layer",
        "session_transcript",
        "data_bank_item",
        "cross_user_authorization",
    }
    missing_sections = required_sections - fixture.keys()
    if missing_sections:
        raise ValueError(f"fixture missing sections: {sorted(missing_sections)}")

    _validate_user_section(fixture["user"])
    _validate_project_section(fixture["project"])
    _validate_owned_section(fixture["character"], "character", required_string_keys=("character_id", "name"))
    _validate_owned_section(fixture["lore_entry"], "lore_entry", required_string_keys=("lore_entry_id", "title"))
    _validate_owned_section(fixture["prompt_layer"], "prompt_layer", required_string_keys=("prompt_layer_id", "layer_name", "content"))
    _validate_session_transcript(fixture["session_transcript"])
    _validate_owned_section(fixture["data_bank_item"], "data_bank_item", required_string_keys=("item_id", "title", "source_type", "excerpt"))
    _validate_cross_user_authorization(fixture["cross_user_authorization"])


def _validate_user_section(section: Any) -> None:
    if not isinstance(section, dict):
        raise ValueError("user must be an object")

    for key in ("user_id", "username", "display_name"):
        if not isinstance(section.get(key), str) or not section.get(key):
            raise ValueError(f"user.{key} is required")

    _validate_provenance(section.get("provenance"), path="user.provenance", require_project=False)


def _validate_project_section(section: Any) -> None:
    if not isinstance(section, dict):
        raise ValueError("project must be an object")

    for key in ("project_id", "user_id", "title"):
        if not isinstance(section.get(key), str) or not section.get(key):
            raise ValueError(f"project.{key} is required")

    provenance = _validate_provenance(section.get("provenance"), path="project.provenance")
    if provenance[0] != section["user_id"]:
        raise ValueError("project.provenance.user_id must match project.user_id")
    if provenance[1] != section["project_id"]:
        raise ValueError("project.provenance.project_id must match project.project_id")


def _validate_owned_section(
    section: Any,
    path: str,
    *,
    required_string_keys: tuple[str, ...],
) -> None:
    if not isinstance(section, dict):
        raise ValueError(f"{path} must be an object")

    for key in ("project_id", "user_id", *required_string_keys):
        if not isinstance(section.get(key), str) or not section.get(key):
            raise ValueError(f"{path}.{key} is required")

    provenance = _validate_provenance(section.get("provenance"), path=f"{path}.provenance")
    if provenance[0] != section["user_id"]:
        raise ValueError(f"{path}.provenance.user_id must match {path}.user_id")
    if provenance[1] != section["project_id"]:
        raise ValueError(f"{path}.provenance.project_id must match {path}.project_id")


def _validate_session_transcript(section: Any) -> None:
    if not isinstance(section, dict):
        raise ValueError("session_transcript must be an object")

    for key in ("session_id", "project_id", "user_id"):
        if not isinstance(section.get(key), str) or not section.get(key):
            raise ValueError(f"session_transcript.{key} is required")

    provenance = _validate_provenance(section.get("provenance"), path="session_transcript.provenance")
    if provenance[0] != section["user_id"]:
        raise ValueError("session_transcript.provenance.user_id must match session_transcript.user_id")
    if provenance[1] != section["project_id"]:
        raise ValueError("session_transcript.provenance.project_id must match session_transcript.project_id")

    messages = section.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("session_transcript.messages must be a non-empty list")

    for index, message in enumerate(messages):
        message_path = f"session_transcript.messages[{index}]"
        if not isinstance(message, dict):
            raise ValueError(f"{message_path} must be an object")
        if not isinstance(message.get("role"), str) or not message.get("role"):
            raise ValueError(f"{message_path}.role is required")
        if not isinstance(message.get("content"), str) or not message.get("content"):
            raise ValueError(f"{message_path}.content is required")
        message_provenance = _validate_provenance(message.get("provenance"), path=f"{message_path}.provenance")
        if message_provenance[0] != section["user_id"]:
            raise ValueError(f"{message_path}.provenance.user_id must match session_transcript.user_id")
        if message_provenance[1] != section["project_id"]:
            raise ValueError(f"{message_path}.provenance.project_id must match session_transcript.project_id")


def _validate_cross_user_authorization(section: Any) -> None:
    if not isinstance(section, dict):
        raise ValueError("cross_user_authorization must be an object")

    for key in ("owner_user_id", "intruder_user_id", "project_id", "resource_id", "resource_user_id", "expected_status"):
        if not isinstance(section.get(key), str) or not section.get(key):
            raise ValueError(f"cross_user_authorization.{key} is required")

    if section["expected_status"] not in {"forbidden", "not_found"}:
        raise ValueError("cross_user_authorization.expected_status must be forbidden or not_found")

    provenance = _validate_provenance(section.get("provenance"), path="cross_user_authorization.provenance")
    if provenance[0] != section["owner_user_id"]:
        raise ValueError("cross_user_authorization.provenance.user_id must match owner_user_id")
    if provenance[1] != section["project_id"]:
        raise ValueError("cross_user_authorization.provenance.project_id must match project_id")
    resource_user_id = section.get("resource_user_id")
    if provenance[2] != resource_user_id:
        raise ValueError("cross_user_authorization.provenance.resource_user_id must match resource_user_id")


def _validate_provenance(provenance: Any, *, path: str, require_project: bool = True) -> tuple[str, str | None, str | None]:
    if not isinstance(provenance, dict):
        raise ValueError(f"{path} is required")

    user_id = provenance.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError(f"{path}.user_id is required")

    project_id = provenance.get("project_id")
    if require_project and (not isinstance(project_id, str) or not project_id):
        raise ValueError(f"{path}.project_id is required")
    if not require_project and project_id is not None and not isinstance(project_id, str):
        raise ValueError(f"{path}.project_id must be a string when provided")

    resource_user_id = provenance.get("resource_user_id")
    if resource_user_id is not None and not isinstance(resource_user_id, str):
        raise ValueError(f"{path}.resource_user_id must be a string when provided")

    return user_id, project_id, resource_user_id


def _index_chapters(chapters: list[Any]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise ValueError(f"chapters[{index}] must be an object")
        number = chapter.get("chapter")
        order = chapter.get("order")
        content = chapter.get("content")
        if not isinstance(number, int):
            raise ValueError(f"chapters[{index}].chapter must be an integer")
        if not isinstance(order, int):
            raise ValueError(f"chapters[{index}].order must be an integer")
        if not isinstance(content, str) or not content:
            raise ValueError(f"chapters[{index}].content must be non-empty text")
        indexed[number] = chapter
    return indexed


def _validate_expected_assertion(
    assertion: Any,
    chapters_by_number: dict[int, dict[str, Any]],
    *,
    path: str,
) -> None:
    if not isinstance(assertion, dict):
        raise ValueError(f"{path} must be an object")

    evidence_text = assertion.get("evidence_text")
    if not isinstance(evidence_text, str) or not evidence_text:
        raise ValueError(f"{path}.evidence_text is required")

    confidence = assertion.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError(f"{path}.confidence must be between 0 and 1")

    source = assertion.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"{path}.source is required")

    chapter_number = source.get("chapter")
    source_order = source.get("order")
    offset_start = source.get("offset_start")
    offset_end = source.get("offset_end")
    if not isinstance(chapter_number, int):
        raise ValueError(f"{path}.source.chapter is required")
    if not isinstance(source_order, int):
        raise ValueError(f"{path}.source.order is required")
    if not isinstance(offset_start, int):
        raise ValueError(f"{path}.source.offset_start is required")
    if not isinstance(offset_end, int):
        raise ValueError(f"{path}.source.offset_end is required")
    if offset_start < 0 or offset_end <= offset_start:
        raise ValueError(f"{path}.source offsets must form a non-empty span")

    chapter = chapters_by_number.get(chapter_number)
    if chapter is None:
        raise ValueError(f"{path}.source.chapter references unknown chapter")
    if chapter["order"] != source_order:
        raise ValueError(f"{path}.source.order does not match chapter order")

    actual_text = chapter["content"][offset_start:offset_end]
    if actual_text != evidence_text:
        raise ValueError(f"{path}.source span must match evidence_text")
