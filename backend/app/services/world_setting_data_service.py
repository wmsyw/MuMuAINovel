"""Shared helpers for dynamic world-setting persistence and prompt context.

The four ``Project.world_*`` columns remain the compatibility projection.  The
JSON document on ``Project.world_setting_data`` is the canonical dynamic
representation, so every writer should use these helpers when it changes one
of the legacy columns.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.schemas.world_setting_template import WorldSettingFieldDefinition

LEGACY_FIELD_MAP: dict[str, str] = {
    "time_period": "world_time_period",
    "location": "world_location",
    "atmosphere": "world_atmosphere",
    "rules": "world_rules",
}

LEGACY_DYNAMIC_FIELDS: dict[str, dict[str, Any]] = {
    "time_period": {"label": "时间设定", "type": "textarea", "required": False},
    "location": {"label": "地点设定", "type": "textarea", "required": False},
    "atmosphere": {"label": "氛围设定", "type": "textarea", "required": False},
    "rules": {"label": "规则设定", "type": "textarea", "required": False},
}


class WorldSettingDataError(ValueError):
    """Raised when a dynamic world-setting document cannot be normalized."""


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorldSettingDataError("世界设定文本字段必须是文本")
    return value.strip() or None


def _field_definitions(raw_fields: Any) -> dict[str, WorldSettingFieldDefinition]:
    if not isinstance(raw_fields, Mapping):
        raw_fields = LEGACY_DYNAMIC_FIELDS
    definitions: dict[str, WorldSettingFieldDefinition] = {}
    for key, value in raw_fields.items():
        if not isinstance(key, str) or not key:
            raise WorldSettingDataError("世界设定字段键不能为空")
        try:
            definitions[key] = (
                value
                if isinstance(value, WorldSettingFieldDefinition)
                else WorldSettingFieldDefinition.model_validate(value)
            )
        except Exception as exc:  # Pydantic's error includes the invalid field path.
            raise WorldSettingDataError(f"世界设定字段定义无效: {key}") from exc
    return definitions


def normalize_world_setting_values(
    definitions: Mapping[str, WorldSettingFieldDefinition],
    values: Mapping[str, Any],
    *,
    reject_unknown: bool = True,
    require_required: bool = True,
) -> dict[str, Any]:
    """Trim dynamic values and enforce their typed/template definitions."""
    if not isinstance(values, Mapping):
        raise WorldSettingDataError("世界设定值必须是对象")
    unknown = set(values) - set(definitions)
    if unknown and reject_unknown:
        raise WorldSettingDataError(f"包含未定义的世界设定字段: {', '.join(sorted(unknown))}")

    normalized: dict[str, Any] = {}
    for key, definition in definitions.items():
        value = values.get(key)
        if definition.type == "list":
            if value is None:
                value = []
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise WorldSettingDataError(f"字段 {definition.label} 必须是文本列表")
            value = [item.strip() for item in value if item.strip()]
            if definition.required and require_required and not value:
                raise WorldSettingDataError(f"字段 {definition.label} 不能为空")
        else:
            if value is not None and not isinstance(value, str):
                raise WorldSettingDataError(f"字段 {definition.label} 必须是文本")
            value = value.strip() if isinstance(value, str) else None
            if definition.required and require_required and not value:
                raise WorldSettingDataError(f"字段 {definition.label} 不能为空")
        normalized[key] = value
    return normalized


def normalize_world_setting_data(
    data: Any,
    *,
    legacy_values: Mapping[str, Any] | None = None,
    default_template_name: str = "旧版世界设定",
    require_required: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe, typed dynamic world-setting document.

    Missing dynamic data is upgraded from the four legacy columns. Existing
    custom definitions and values are retained; values are trimmed according
    to their declared type.
    """
    raw = data if isinstance(data, Mapping) else {}
    definitions = _field_definitions(raw.get("fields"))
    source_values: dict[str, Any] = {}
    raw_values = raw.get("values")
    if isinstance(raw_values, Mapping):
        source_values.update(raw_values)
    if legacy_values:
        for dynamic_key, legacy_key in LEGACY_FIELD_MAP.items():
            if legacy_key not in legacy_values:
                continue
            if dynamic_key not in definitions:
                definitions[dynamic_key] = WorldSettingFieldDefinition.model_validate(LEGACY_DYNAMIC_FIELDS[dynamic_key])
            if dynamic_key not in source_values:
                source_values[dynamic_key] = legacy_values.get(legacy_key)
    values = normalize_world_setting_values(
        definitions,
        source_values,
        require_required=require_required,
    )
    return {
        "template_id": raw.get("template_id"),
        "template_name": raw.get("template_name") or default_template_name,
        "fields": {key: definition.model_dump(mode="json") for key, definition in definitions.items()},
        "values": values,
    }


def project_world_setting_data(project: Any) -> dict[str, Any]:
    """Read a project document, upgrading legacy-only projects in memory."""
    legacy_values = {key: getattr(project, key, None) for key in LEGACY_FIELD_MAP.values()}
    try:
        return normalize_world_setting_data(
            getattr(project, "world_setting_data", None),
            legacy_values=legacy_values,
            default_template_name="基础世界设定",
            require_required=False,
        )
    except WorldSettingDataError:
        # A malformed old document must not prevent generation. Keep all
        # legacy projections and fall back to the known typed fields.
        return normalize_world_setting_data(
            None,
            legacy_values=legacy_values,
            default_template_name="基础世界设定",
            require_required=False,
        )


def merge_project_world_setting_data(
    project: Any,
    *,
    legacy_updates: Mapping[str, Any] | None = None,
    dynamic_updates: Mapping[str, Any] | None = None,
    replace_data: Any = None,
) -> dict[str, Any]:
    """Synchronize a project's dynamic document with legacy field writes.

    ``dynamic_updates`` may include custom fields. Legacy updates only touch
    the corresponding dynamic keys and never erase unrelated custom values.
    """
    legacy_values = {key: getattr(project, key, None) for key in LEGACY_FIELD_MAP.values()}
    data = normalize_world_setting_data(
        replace_data if replace_data is not None else getattr(project, "world_setting_data", None),
        legacy_values=legacy_values,
        default_template_name="基础世界设定",
        require_required=False,
    )
    definitions = _field_definitions(data["fields"])
    if legacy_updates:
        for dynamic_key, legacy_key in LEGACY_FIELD_MAP.items():
            if legacy_key in legacy_updates and dynamic_key not in definitions:
                definitions[dynamic_key] = WorldSettingFieldDefinition.model_validate(LEGACY_DYNAMIC_FIELDS[dynamic_key])
    values = dict(data["values"])
    if legacy_updates:
        for dynamic_key, legacy_key in LEGACY_FIELD_MAP.items():
            if legacy_key in legacy_updates:
                values[dynamic_key] = _string_value(legacy_updates.get(legacy_key))
    if dynamic_updates:
        values.update(deepcopy(dict(dynamic_updates)))
    data["fields"] = {key: definition.model_dump(mode="json") for key, definition in definitions.items()}
    data["values"] = normalize_world_setting_values(
        definitions,
        values,
        require_required=False,
    )
    project.world_setting_data = data
    return data


def legacy_values_from_dynamic(values: Mapping[str, Any]) -> dict[str, str | None]:
    """Build the compatibility projection from normalized dynamic values."""
    result: dict[str, str | None] = {}
    for dynamic_key, legacy_key in LEGACY_FIELD_MAP.items():
        value = values.get(dynamic_key)
        result[legacy_key] = value.strip() if isinstance(value, str) and value.strip() else None
    return result


def dynamic_world_setting_context(project: Any) -> str:
    """Format dynamic-only fields for AI prompts without dropping legacy fields."""
    data = project_world_setting_data(project)
    values = data.get("values", {})
    definitions = data.get("fields", {})
    dynamic_lines: list[str] = []
    for key, raw_definition in definitions.items():
        if key in LEGACY_FIELD_MAP:
            continue
        definition = raw_definition if isinstance(raw_definition, Mapping) else {}
        label = str(definition.get("label") or key)
        value = values.get(key)
        if isinstance(value, list):
            rendered = "、".join(item for item in value if isinstance(item, str) and item.strip())
        else:
            rendered = str(value or "").strip()
        if rendered:
            dynamic_lines.append(f"- {label}（{key}）：{rendered}")
    if not dynamic_lines:
        return ""
    template_name = data.get("template_name") or "自定义世界设定"
    return "动态世界设定（{template_name}）：\n{lines}".format(
        template_name=template_name,
        lines="\n".join(dynamic_lines),
    )


def world_setting_context(project: Any, *, include_dynamic: bool = True) -> str:
    """Format the legacy projection plus dynamic-only fields for prompts."""
    lines = [
        f"时间背景：{getattr(project, 'world_time_period', None) or '未设定'}",
        f"地理位置：{getattr(project, 'world_location', None) or '未设定'}",
        f"氛围基调：{getattr(project, 'world_atmosphere', None) or '未设定'}",
        f"世界规则：{getattr(project, 'world_rules', None) or '未设定'}",
    ]
    if include_dynamic:
        dynamic = dynamic_world_setting_context(project)
        if dynamic:
            lines.extend(["", dynamic])
    return "\n".join(lines)


def dynamic_prompt_values(project: Any) -> dict[str, str]:
    """Return common legacy prompt values and a dynamic context placeholder."""
    return {
        "time_period": getattr(project, "world_time_period", None) or "未设定",
        "location": getattr(project, "world_location", None) or "未设定",
        "atmosphere": getattr(project, "world_atmosphere", None) or "未设定",
        "rules": getattr(project, "world_rules", None) or "未设定",
        "dynamic_world_setting": dynamic_world_setting_context(project),
        "world_setting_context": world_setting_context(project),
    }
