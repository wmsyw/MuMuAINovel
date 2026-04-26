from __future__ import annotations

# pyright: reportAny=false

from copy import deepcopy

from collections.abc import Callable

from .fixture_schema import load_golden_fixture, validate_golden_fixture


def test_validator_accepts_valid_golden_fixture() -> None:
    fixture = load_golden_fixture()

    validate_golden_fixture(fixture)


def test_validator_rejects_missing_evidence_text() -> None:
    fixture = load_golden_fixture()
    malformed_fixture = deepcopy(fixture)
    del malformed_fixture["expected"]["characters"][0]["evidence_text"]

    _assert_validation_error(lambda: validate_golden_fixture(malformed_fixture), "evidence_text")


def test_validator_rejects_missing_confidence() -> None:
    fixture = load_golden_fixture()
    malformed_fixture = deepcopy(fixture)
    del malformed_fixture["expected"]["world_facts"][0]["confidence"]

    _assert_validation_error(lambda: validate_golden_fixture(malformed_fixture), "confidence")


def test_validator_rejects_missing_source_chapter_and_order() -> None:
    fixture = load_golden_fixture()
    malformed_fixture = deepcopy(fixture)
    source = malformed_fixture["expected"]["relationships"][0]["source"]
    del source["chapter"]
    del source["order"]

    _assert_validation_error(lambda: validate_golden_fixture(malformed_fixture), "source.chapter")


def test_validator_rejects_missing_source_span() -> None:
    fixture = load_golden_fixture()
    malformed_fixture = deepcopy(fixture)
    del malformed_fixture["expected"]["contradictory_evidence"][0]["source"]["offset_start"]

    _assert_validation_error(lambda: validate_golden_fixture(malformed_fixture), "offset_start")


def test_validator_rejects_source_span_that_does_not_match_evidence() -> None:
    fixture = load_golden_fixture()
    malformed_fixture = deepcopy(fixture)
    malformed_fixture["expected"]["organization_affiliations"][0]["source"]["offset_end"] -= 1

    _assert_validation_error(lambda: validate_golden_fixture(malformed_fixture), "span must match evidence_text")


def _assert_validation_error(action: Callable[[], None], expected_message: str) -> None:
    try:
        action()
    except ValueError as error:
        assert expected_message in str(error)
    else:
        raise AssertionError(f"expected ValueError containing {expected_message!r}")
