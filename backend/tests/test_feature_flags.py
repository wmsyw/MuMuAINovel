from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

import importlib

import pytest

from app import feature_flags


FLAG_DEFAULTS = {
    "creative_sessions_enabled": False,
    "lorebook_injection_enabled": False,
    "prompt_trace_enabled": True,
    "prompt_presets_enabled": False,
    "rag_injection_enabled": False,
    "quick_actions_enabled": False,
    "voice_personas_enabled": False,
    "group_scene_simulation_enabled": False,
    "local_assets_enabled": False,
}


def test_feature_flag_defaults_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    for flag_name in FLAG_DEFAULTS:
        monkeypatch.delenv(flag_name.upper(), raising=False)

    module = importlib.reload(feature_flags)

    assert module.FEATURE_FLAG_DEFAULTS == FLAG_DEFAULTS
    for flag_name, expected in FLAG_DEFAULTS.items():
        assert module.is_enabled(flag_name) is expected


def test_feature_flag_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREATIVE_SESSIONS_ENABLED", "true")
    monkeypatch.setenv("PROMPT_TRACE_ENABLED", "false")

    module = importlib.reload(feature_flags)

    assert module.is_enabled("creative_sessions_enabled") is True
    assert module.is_enabled("prompt_trace_enabled") is False
