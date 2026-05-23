# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

import json

from .fixture_schema import REQUIRED_EXPECTED_CATEGORIES, load_golden_fixture, load_workflow_fixture


def test_golden_fixture_has_required_expected_sections() -> None:
    fixture = load_golden_fixture()

    assert REQUIRED_EXPECTED_CATEGORIES <= fixture["expected"].keys()


def test_fixture_generation_is_deterministic() -> None:
    first = _canonical_fixture_bytes()
    second = _canonical_fixture_bytes()

    assert first == second


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


def test_workflow_fixture_covers_user_project_character_lore_prompt_session_and_databank() -> None:
    fixture = load_workflow_fixture()

    assert fixture["fixture_id"] == "novel_workflow_provenance_golden_v1"
    assert fixture["user"]["display_name"] == "梁知夏"
    assert fixture["project"]["title"] == "银灯纪行"
    assert fixture["character"]["aliases"] == ["青岚", "阿岚"]
    assert fixture["character"]["provenance"]["project_id"] == fixture["project"]["project_id"]
    assert fixture["lore_entry"]["content"] == "潮汐钟以月潮驱动霁月城的昼夜结界。"
    assert fixture["prompt_layer"]["content"].startswith("保持第一人称内心独白")
    assert [message["role"] for message in fixture["session_transcript"]["messages"]] == ["user", "assistant"]
    assert fixture["session_transcript"]["messages"][1]["content"] == "雨水敲在青石板上，林青岚把披风拢紧。"
    assert fixture["data_bank_item"]["source_type"] == "txt_upload"


def test_workflow_fixture_tracks_cross_user_authorization_provenance() -> None:
    fixture = load_workflow_fixture()
    authorization = fixture["cross_user_authorization"]

    assert authorization["owner_user_id"] == fixture["user"]["user_id"]
    assert authorization["intruder_user_id"] == "user-rival-002"
    assert authorization["expected_status"] == "forbidden"
    assert authorization["provenance"]["project_id"] == fixture["project"]["project_id"]
    assert authorization["provenance"]["resource_user_id"] == fixture["user"]["user_id"]


def _canonical_fixture_bytes() -> bytes:
    return json.dumps(
        {
            "extraction": load_golden_fixture(),
            "workflow": load_workflow_fixture(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
