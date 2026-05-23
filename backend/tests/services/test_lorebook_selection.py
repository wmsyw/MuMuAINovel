from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false

from app.services.lorebook_service import LorebookCandidate, select_lorebook_entries


def _fixture_candidates() -> list[LorebookCandidate]:
    return [
        LorebookCandidate(
            id="realm",
            title="龙城",
            content="R" * 20,
            activation_keys=("龙城", "Dragon City"),
            priority=10,
        ),
        LorebookCandidate(
            id="order",
            title="青岚阁",
            content="O" * 10,
            activation_keys=("青岚阁",),
            priority=30,
        ),
        LorebookCandidate(
            id="disabled",
            title="禁用高优先级",
            content="D" * 10,
            activation_keys=("龙城",),
            priority=100,
            enabled=False,
        ),
        LorebookCandidate(
            id="unmatched",
            title="未触发",
            content="U" * 10,
            activation_keys=("不存在",),
            priority=99,
        ),
    ]


def test_selection_is_deterministic_by_enabled_activation_and_priority() -> None:
    activation_text = "主角抵达龙城，青岚阁正在等待。"

    first = select_lorebook_entries(_fixture_candidates(), activation_text=activation_text)
    second = select_lorebook_entries(_fixture_candidates(), activation_text=activation_text)

    assert [item.id for item in first.items] == ["order", "realm"]
    assert [item.id for item in second.items] == ["order", "realm"]
    assert first == second
    assert first.total_candidates == 4
    assert first.items[0].matched_keys == ("青岚阁",)
    assert first.items[1].matched_keys == ("龙城",)


def test_disabled_entries_are_excluded_even_when_keys_match() -> None:
    selection = select_lorebook_entries(
        [LorebookCandidate(id="disabled", title="禁用", content="secret", activation_keys=("secret",), priority=999, enabled=False)],
        activation_text="secret",
    )

    assert selection.selected_count == 0
    assert selection.chars_used == 0


def test_character_budget_trims_over_budget_entries_predictably() -> None:
    selection = select_lorebook_entries(
        _fixture_candidates(),
        activation_text="青岚阁与龙城同时出现",
        max_chars=15,
    )

    assert selection.budget_chars == 15
    assert selection.chars_used == 15
    assert [item.id for item in selection.items] == ["order", "realm"]
    assert selection.items[0].content == "O" * 10
    assert selection.items[0].trimmed is False
    assert selection.items[1].content == "RRRR…"
    assert selection.items[1].selected_content_length == 5
    assert selection.items[1].original_content_length == 20
    assert selection.items[1].trimmed is True


def test_token_budget_uses_deterministic_character_estimate() -> None:
    selection = select_lorebook_entries(
        _fixture_candidates(),
        activation_text="青岚阁与龙城同时出现",
        max_tokens=3,
        chars_per_token=4,
    )

    assert selection.budget_chars == 12
    assert selection.chars_used == 12
    assert [item.id for item in selection.items] == ["order", "realm"]
    assert selection.items[1].content == "R…"


def test_same_priority_tiebreaks_by_first_key_position_title_and_id() -> None:
    candidates = [
        LorebookCandidate(id="b", title="乙", content="B", activation_keys=("后",), priority=5),
        LorebookCandidate(id="a2", title="甲", content="A2", activation_keys=("同",), priority=5),
        LorebookCandidate(id="a1", title="甲", content="A1", activation_keys=("同",), priority=5),
    ]

    selection = select_lorebook_entries(candidates, activation_text="同在前，后在后")

    assert [item.id for item in selection.items] == ["a1", "a2", "b"]
