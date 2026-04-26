# pyright: reportAny=false

from .fixture_schema import REQUIRED_EXPECTED_CATEGORIES, load_golden_fixture


def test_golden_fixture_has_required_expected_sections() -> None:
    fixture = load_golden_fixture()

    assert REQUIRED_EXPECTED_CATEGORIES <= fixture["expected"].keys()


def test_fixture_covers_two_aliases_for_one_character() -> None:
    fixture = load_golden_fixture()
    character = fixture["expected"]["characters"][0]

    assert character["canonical_name"] == "林青岚"
    assert character["aliases"] == ["青岚", "阿岚"]


def test_fixture_covers_organization_affiliation_change() -> None:
    fixture = load_golden_fixture()
    affiliation = fixture["expected"]["organization_affiliations"][0]

    assert affiliation["previous_organization"] == "摘星阁"
    assert affiliation["current_organization"] == "巡星司"


def test_fixture_covers_profession_change() -> None:
    fixture = load_golden_fixture()
    profession_states = fixture["expected"]["profession_changes"]

    assert [state["profession"] for state in profession_states] == ["抄书学徒", "星图测绘师"]
    assert [state["state"] for state in profession_states] == ["initial", "changed"]


def test_fixture_covers_relationship_start_change_and_end() -> None:
    fixture = load_golden_fixture()
    relationship_states = fixture["expected"]["relationships"]

    states_by_name = {relationship["state"] for relationship in relationship_states}

    assert states_by_name == {"started", "changed", "ended"}
    assert all(relationship["participants"] == ["林青岚", "沈砚"] for relationship in relationship_states)


def test_fixture_covers_world_fact() -> None:
    fixture = load_golden_fixture()
    world_fact = fixture["expected"]["world_facts"][0]

    assert world_fact["subject"] == "霁月城"
    assert "潮汐钟" in world_fact["fact"]


def test_fixture_covers_ambiguous_duplicate_name() -> None:
    fixture = load_golden_fixture()
    duplicate = fixture["expected"]["ambiguous_duplicate_names"][0]

    assert duplicate["name"] == "林青岚"
    assert duplicate["resolution"] == "requires_manual_review"


def test_fixture_covers_contradictory_evidence_case() -> None:
    fixture = load_golden_fixture()
    contradictory_claims = fixture["expected"]["contradictory_evidence"]

    assert {claim["contradiction_group"] for claim in contradictory_claims} == {"青岚第三章所在位置"}
    assert {claim["claim"] for claim in contradictory_claims} == {
        "青岚当夜在北门点燃信号",
        "青岚同一时刻被关在摘星阁地牢",
    }


def test_all_expected_assertions_have_matching_source_spans() -> None:
    fixture = load_golden_fixture()
    chapters = {chapter["chapter"]: chapter for chapter in fixture["chapters"]}

    for assertions in fixture["expected"].values():
        for assertion in assertions:
            source = assertion["source"]
            content = chapters[source["chapter"]]["content"]
            assert content[source["offset_start"]:source["offset_end"]] == assertion["evidence_text"]
