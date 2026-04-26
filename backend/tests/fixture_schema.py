from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnnecessaryIsInstance=false, reportUnreachable=false

import json
from pathlib import Path
from typing import Any


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "novel_extraction_golden.json"

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
