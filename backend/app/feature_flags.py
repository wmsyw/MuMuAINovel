"""Centralized feature flag helpers for workflow waves.

The flags are loaded from environment variables or the repo .env file via
Pydantic settings, but defaults remain explicitly declared here for auditability.
"""

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUntypedFunctionDecorator=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict


FEATURE_FLAG_DEFAULTS: Final[dict[str, bool]] = {
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


class FeatureFlagSettings(BaseSettings):
    """Environment-backed feature flag settings."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    creative_sessions_enabled: bool = FEATURE_FLAG_DEFAULTS["creative_sessions_enabled"]
    lorebook_injection_enabled: bool = FEATURE_FLAG_DEFAULTS["lorebook_injection_enabled"]
    prompt_trace_enabled: bool = FEATURE_FLAG_DEFAULTS["prompt_trace_enabled"]
    prompt_presets_enabled: bool = FEATURE_FLAG_DEFAULTS["prompt_presets_enabled"]
    rag_injection_enabled: bool = FEATURE_FLAG_DEFAULTS["rag_injection_enabled"]
    quick_actions_enabled: bool = FEATURE_FLAG_DEFAULTS["quick_actions_enabled"]
    voice_personas_enabled: bool = FEATURE_FLAG_DEFAULTS["voice_personas_enabled"]
    group_scene_simulation_enabled: bool = FEATURE_FLAG_DEFAULTS["group_scene_simulation_enabled"]
    local_assets_enabled: bool = FEATURE_FLAG_DEFAULTS["local_assets_enabled"]


_feature_flags = FeatureFlagSettings()


def is_enabled(flag_name: str) -> bool:
    """Return whether a feature flag is enabled.

    Unknown names are treated as disabled to keep the runtime safe by default.
    """

    return bool(getattr(_feature_flags, flag_name, FEATURE_FLAG_DEFAULTS.get(flag_name, False)))
