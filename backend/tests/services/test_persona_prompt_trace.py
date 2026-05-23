from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false

from types import SimpleNamespace
from typing import Any

import pytest

from app import feature_flags
from app.services.prompt_service import PromptService


def _fixture_voice_persona() -> SimpleNamespace:
    return SimpleNamespace(
        id="voice-persona-rain-noir",
        project_id="project-persona-trace",
        user_id="user-persona-trace",
        session_id=None,
        scope="project",
        name="雨夜冷峻旁白",
        tone="克制、冷峻、带轻微悬疑压迫感",
        style="短句推进，环境细节服务人物行动",
        point_of_view="第三人称限知",
        constraints="避免作者评论；不要替角色解释动机，只呈现可观察行为。",
    )


def _fixture_trace() -> dict[str, Any]:
    return PromptService.build_voice_persona_prompt_trace(
        _fixture_voice_persona(),
        project_id="project-persona-trace",
        session_id="session-persona-trace",
        chars_per_token=2,
    )


def test_voice_persona_trace_is_stable() -> None:
    first = _fixture_trace()
    second = _fixture_trace()

    assert first == second
    assert first["source_type"] == "voice_persona"
    assert first["schema_version"] == "voice-persona-prompt-trace/v1"
    assert first["trace_id"].startswith("vpt_")
    assert first["selected_voice_persona_id"] == "voice-persona-rain-noir"
    assert first["project_id"] == "project-persona-trace"
    assert first["session_id"] == "session-persona-trace"
    assert first["profile_scope"] == "project"
    assert first["applied_scope"] == "session"
    assert first["source_order"] == 35
    assert first["items"][0]["order"] == 1
    assert first["items"][0]["source_order"] == 35
    assert first["items"][0]["trace_id"] == first["trace_id"]
    assert first["items"][0]["source_type"] == "voice_persona"
    assert first["profile"] == {
        "id": "voice-persona-rain-noir",
        "name": "雨夜冷峻旁白",
        "tone": "克制、冷峻、带轻微悬疑压迫感",
        "style": "短句推进，环境细节服务人物行动",
        "point_of_view": "第三人称限知",
        "constraints": "避免作者评论；不要替角色解释动机，只呈现可观察行为。",
        "scope": "project",
    }
    assert first["final_preview_text"] == (
        "### Narrator Voice: 雨夜冷峻旁白 [voice-persona-rain-noir]\n"
        "Tone: 克制、冷峻、带轻微悬疑压迫感\n"
        "Style: 短句推进，环境细节服务人物行动\n"
        "POV: 第三人称限知\n"
        "Constraints:\n"
        "避免作者评论；不要替角色解释动机，只呈现可观察行为。"
    )


def test_voice_persona_flag_off_preserves_baseline_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feature_flags, "is_enabled", lambda flag_name: False)
    baseline_prompt = "原始章节提示词"

    assembled = PromptService.apply_voice_persona_prompt_trace(
        baseline_prompt,
        _fixture_trace(),
        injection_enabled=feature_flags.is_enabled("voice_personas_enabled"),
    )

    assert assembled == baseline_prompt


def test_voice_persona_trace_appends_only_when_explicitly_enabled() -> None:
    baseline_prompt = "原始章节提示词"
    trace = _fixture_trace()

    assembled = PromptService.apply_voice_persona_prompt_trace(
        baseline_prompt,
        trace,
        injection_enabled=True,
    )

    assert assembled.startswith(baseline_prompt)
    assert "<voice_persona_context source_type=\"voice_persona\"" in assembled
    assert f"trace_id=\"{trace['trace_id']}\"" in assembled
    assert "已选择ID: voice-persona-rain-noir" in assembled
    assert "第三人称限知" in assembled
