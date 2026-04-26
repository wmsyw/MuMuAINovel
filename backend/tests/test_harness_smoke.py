# pyright: reportAny=false

from .fixture_schema import load_golden_fixture


def test_pytest_harness_loads_golden_fixture() -> None:
    fixture = load_golden_fixture()

    assert fixture["fixture_id"] == "novel_extraction_chinese_golden_v1"
    assert len(fixture["chapters"]) == 3
    assert "林青岚" in fixture["chapters"][0]["content"]
