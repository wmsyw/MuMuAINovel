from __future__ import annotations

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownParameterType=false, reportUnknownMemberType=false, reportUnknownLambdaType=false

import pytest

from app import feature_flags
from app.services.data_bank_service import DataBankRetrievalResult, DataBankRetrievalTrace
from app.services.prompt_service import PromptService


def _fixture_retrieval_trace() -> DataBankRetrievalTrace:
    return DataBankRetrievalTrace(
        project_id="project-rag-preview",
        query="龙城 玄铁",
        total_candidates=3,
        returned_count=2,
        results=(
            DataBankRetrievalResult(
                order=1,
                item_id="data-bank-item-city",
                chunk_id="chunk-city-001",
                title="龙城资料卡",
                source_type="snippet",
                filename=None,
                chunk_index=0,
                score=7.0,
                matched_terms=("龙城", "玄铁"),
                content="龙城建立在七层玄铁城墙之上，城门只在月蚀夜完全开启。",
                char_start=0,
                char_end=30,
                content_hash="hash-city",
            ),
            DataBankRetrievalResult(
                order=2,
                item_id="data-bank-item-order",
                chunk_id="chunk-order-001",
                title="青岚阁备忘",
                source_type="upload",
                filename="order.md",
                chunk_index=1,
                score=1.0,
                matched_terms=("龙城",),
                content="青岚阁曾派密探潜入龙城，留下半枚铜符作为接头凭证。",
                char_start=12,
                char_end=42,
                content_hash="hash-order",
            ),
        ),
    )


def test_preview_contains_source_trace() -> None:
    first = PromptService.build_rag_prompt_trace(_fixture_retrieval_trace(), max_excerpt_chars=24, chars_per_token=2)
    second = PromptService.build_rag_prompt_trace(_fixture_retrieval_trace(), max_excerpt_chars=24, chars_per_token=2)

    assert first == second
    assert first["source_type"] == "rag"
    assert first["retrieval_source"] == "data_bank"
    assert first["strategy"] == "deterministic-lexical-v1"
    assert first["project_id"] == "project-rag-preview"
    assert first["query"] == "龙城 玄铁"
    assert first["selected_source_ids"] == ["data-bank-item-city", "data-bank-item-order"]
    assert first["selected_count"] == 2
    assert first["total_candidates"] == 3

    assert [item["order"] for item in first["items"]] == [1, 2]
    assert [item["source_id"] for item in first["items"]] == ["data-bank-item-city", "data-bank-item-order"]
    assert [item["title"] for item in first["items"]] == ["龙城资料卡", "青岚阁备忘"]
    assert [item["score"] for item in first["items"]] == [7.0, 1.0]
    assert first["items"][0]["excerpt"] == "龙城建立在七层玄铁城墙之上，城门只在月蚀夜完全…"
    assert first["items"][1]["excerpt"] == "青岚阁曾派密探潜入龙城，留下半枚铜符作为接头凭…"
    assert first["items"][0]["chunk_id"] == "chunk-city-001"
    assert first["items"][1]["filename"] == "order.md"
    assert "### 1. 龙城资料卡 [data-bank-item-city]" in first["final_preview_text"]
    assert "评分: 7" in first["final_preview_text"]


def test_rag_flag_off_preserves_baseline_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feature_flags, "is_enabled", lambda flag_name: False)
    baseline_prompt = "原始章节提示词\n第二行保持不变"
    trace = PromptService.build_rag_prompt_trace(_fixture_retrieval_trace())

    assembled = PromptService.apply_rag_prompt_trace(
        baseline_prompt,
        trace,
        injection_enabled=feature_flags.is_enabled("rag_injection_enabled"),
    )

    assert assembled == baseline_prompt


def test_rag_trace_appends_only_when_explicitly_enabled() -> None:
    baseline_prompt = "原始章节提示词"
    trace = PromptService.build_rag_prompt_trace(_fixture_retrieval_trace())

    assembled = PromptService.apply_rag_prompt_trace(
        baseline_prompt,
        trace,
        injection_enabled=True,
    )

    assert assembled.startswith(baseline_prompt)
    assert "<rag_context source_type=\"data_bank\">" in assembled
    assert "已选择来源ID: data-bank-item-city, data-bank-item-order" in assembled
    assert "龙城建立在七层玄铁城墙之上" in assembled
