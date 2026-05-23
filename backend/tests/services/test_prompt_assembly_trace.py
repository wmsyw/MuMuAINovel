from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false

import pytest
from typing import Any

from app import feature_flags
from app.services.lorebook_service import LorebookCandidate, select_lorebook_entries
from app.services.prompt_service import PromptService


def _fixture_trace() -> dict[str, Any]:
    candidates = [
        LorebookCandidate(
            id="lore-city",
            title="龙城",
            content="龙城建立在七层玄铁城墙之上。",
            activation_keys=("龙城",),
            priority=20,
            source_type="manual",
        ),
        LorebookCandidate(
            id="lore-order",
            title="青岚阁",
            content="青岚阁只在暴雨夜打开山门。",
            activation_keys=("青岚阁",),
            priority=30,
            source_type="imported",
        ),
    ]
    selection = select_lorebook_entries(
        candidates,
        activation_text="青岚阁派人前往龙城。",
        max_tokens=12,
        chars_per_token=2,
    )
    return PromptService.build_lorebook_prompt_trace(selection, chars_per_token=2)


def test_lorebook_trace_is_deterministic_with_ids_order_budget_and_preview() -> None:
    first = _fixture_trace()
    second = _fixture_trace()

    assert first == second
    assert first["source_type"] == "lorebook"
    assert first["selected_lore_ids"] == ["lore-order", "lore-city"]
    assert first["budget_estimate"] == {
        "chars_used": 24,
        "budget_chars": 24,
        "estimated_tokens": 12,
        "chars_per_token": 2,
    }
    assert [item["order"] for item in first["items"]] == [1, 2]
    assert [item["source_type"] for item in first["items"]] == ["lorebook", "lorebook"]
    assert [item["entry_source_type"] for item in first["items"]] == ["imported", "manual"]
    assert first["final_preview_text"] == (
        "### 1. 青岚阁 [lore-order]\n"
        "来源: lorebook/imported\n"
        "匹配关键词: 青岚阁\n"
        "青岚阁只在暴雨夜打开山门。\n\n"
        "### 2. 龙城 [lore-city]\n"
        "来源: lorebook/manual\n"
        "匹配关键词: 龙城\n"
        "龙城建立在七层玄铁城…"
    )


def test_lorebook_flag_off_preserves_baseline_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feature_flags, "is_enabled", lambda flag_name: False)
    baseline_prompt = "原始章节提示词"

    assembled = PromptService.apply_lorebook_prompt_trace(
        baseline_prompt,
        _fixture_trace(),
        injection_enabled=feature_flags.is_enabled("lorebook_injection_enabled"),
    )

    assert assembled == baseline_prompt


def test_lorebook_trace_appends_only_when_explicitly_enabled() -> None:
    baseline_prompt = "原始章节提示词"
    assembled = PromptService.apply_lorebook_prompt_trace(
        baseline_prompt,
        _fixture_trace(),
        injection_enabled=True,
    )

    assert assembled.startswith(baseline_prompt)
    assert "<lorebook_context source_type=\"lorebook\">" in assembled
    assert "已选择ID: lore-order, lore-city" in assembled
    assert "青岚阁只在暴雨夜打开山门" in assembled


def _assembly_layers() -> list[dict[str, Any]]:
    return [
        {
            "id": "user-instruction",
            "source_type": "user_instruction",
            "label": "本次要求",
            "content": "写出暴雨夜的压迫感。",
            "metadata": {"request": "chapter-preview"},
        },
        {
            "id": "system-template",
            "source_type": "system_template",
            "label": "系统模板",
            "content": "你是长篇小说作者。",
            "metadata": {"template_key": "CHAPTER_GENERATION_ONE_TO_MANY"},
        },
        {
            "id": "lorebook-context",
            "source_type": "lorebook",
            "label": "Lorebook",
            "content": "龙城建立在七层玄铁城墙之上。",
            "metadata": {"selected_lore_ids": ["lore-city"]},
        },
    ]


def test_same_inputs_same_trace() -> None:
    first = PromptService.build_prompt_assembly_trace(_assembly_layers())
    second = PromptService.build_prompt_assembly_trace(_assembly_layers())

    assert first == second
    assert first["trace_version"] == 1
    assert first["schema_version"] == "prompt-assembly-trace/v1"
    assert first["preset_boundary"] == "prompt_workshop"
    assert first["validation"]["valid"] is True
    assert first["layer_order"] == ["system-template", "lorebook-context", "user-instruction"]
    assert [layer["order"] for layer in first["layers"]] == [1, 2, 3]
    assert first["final_prompt"] == (
        "你是长篇小说作者。\n\n"
        "龙城建立在七层玄铁城墙之上。\n\n"
        "写出暴雨夜的压迫感。"
    )
    assert first["trace_id"].startswith("pat_")


def test_invalid_assembly_layer_reports_validation_error() -> None:
    trace = PromptService.build_prompt_assembly_trace(
        [
            {"id": "bad", "source_type": "script", "content": "print('hidden mutation')"},
            {"id": "bad", "source_type": "manual", "content": "重复ID"},
        ]
    )

    assert trace["validation"]["valid"] is False
    messages = [error["message"] for error in trace["validation"]["errors"]]
    assert "禁止的提示词层来源: script" in messages
    assert "重复的提示词层 id: bad" in messages
