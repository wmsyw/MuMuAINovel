from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownMemberType=false, reportAny=false, reportExplicitAny=false

from types import SimpleNamespace
from typing import Any

from app.services.prompt_service import PromptService


def _fixture_trace() -> dict[str, Any]:
    project = SimpleNamespace(id="project-group-trace", title="长夜边城")
    participants = [
        SimpleNamespace(
            id="char-shen-ce",
            name="沈策",
            role_type="protagonist",
            personality="克制谨慎，擅长反问。",
            speech_patterns="短句、讽刺、少解释。",
            motivations="守住边境军权。",
            arc_summary="从被动防守转向主动布局。",
        ),
        SimpleNamespace(
            id="char-lu-wanshuang",
            name="陆晚霜",
            role_type="supporting",
            personality="温和但锐利。",
            speech_patterns="语调平稳，以事实施压。",
            motivations="查明密诏真相。",
            arc_summary="从旁观者成为局中人。",
        ),
    ]
    voice_persona = SimpleNamespace(
        id="voice-court-noir",
        project_id="project-group-trace",
        user_id="user-group-trace",
        session_id=None,
        scope="project",
        name="冷峻宫廷旁白",
        tone="压抑、克制",
        style="多潜台词，少解释",
        point_of_view="第三人称限知",
        constraints="不要作者跳出点评。",
    )
    lore_entries = [
        SimpleNamespace(
            id="lore-secret-edict",
            title="北境密诏",
            content="皇帝曾下密诏要求北境军不得擅离关隘，否则视为谋逆。",
            source_type="manual",
            activation_keys=["密诏", "北境"],
        )
    ]
    return PromptService.build_group_scene_prompt_trace(
        project=project,
        participants=participants,
        scenario="雨夜书房中，两人围绕密诏互相试探。",
        voice_persona=voice_persona,
        lore_entries=lore_entries,
        prompt_context="参考上一章结尾的火漆细节。",
        chars_per_token=2,
    )


def test_group_scene_trace_is_stable_and_bounded() -> None:
    first = _fixture_trace()
    second = _fixture_trace()

    assert first == second
    assert first["source_type"] == "group_scene"
    assert first["schema_version"] == "group-scene-prompt-trace/v1"
    assert first["trace_id"].startswith("gst_")
    assert first["project_id"] == "project-group-trace"
    assert first["participant_character_ids"] == ["char-shen-ce", "char-lu-wanshuang"]
    assert first["selected_voice_persona_id"] == "voice-court-noir"
    assert first["selected_lore_ids"] == ["lore-secret-edict"]
    assert first["selected_prompt_context"] == "参考上一章结尾的火漆细节。"
    assert first["boundary_decision"] == "writing_artifact_only"
    assert first["source_order"] == 65
    assert first["participants"][0]["source_type"] == "project_character"
    assert first["voice_persona_trace"]["source_type"] == "voice_persona"
    assert "Writing-only group scene artifact" in first["final_preview_text"]
    assert "autonomous_chat_loop" in first["forbidden_runtime_semantics"]
    assert "automatic_chapter_rewrite" in first["forbidden_runtime_semantics"]
