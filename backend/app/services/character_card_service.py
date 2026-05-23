"""角色卡片字段与原生 JSON 校验辅助。"""

from __future__ import annotations

from typing import Any


CHARACTER_CARD_VERSION = 1
CHARACTER_CARD_FIELDS = (
    "writing_notes",
    "speech_patterns",
    "motivations",
    "arc_summary",
    "card_version",
)
CHARACTER_CARD_TEXT_FIELDS = (
    "writing_notes",
    "speech_patterns",
    "motivations",
    "arc_summary",
)


def character_card_field_values(source: Any) -> dict[str, Any]:
    """Return the writing-focused card fields from a model-like object."""

    card_version = getattr(source, "card_version", None)
    if card_version is None:
        card_version = CHARACTER_CARD_VERSION

    return {
        "writing_notes": getattr(source, "writing_notes", None),
        "speech_patterns": getattr(source, "speech_patterns", None),
        "motivations": getattr(source, "motivations", None),
        "arc_summary": getattr(source, "arc_summary", None),
        "card_version": card_version,
    }


def normalize_character_card_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize validated card fields for persistence."""

    normalized: dict[str, Any] = {}
    for field in CHARACTER_CARD_TEXT_FIELDS:
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field}字段必须是字符串")
        normalized[field] = value

    card_version = payload.get("card_version")
    if card_version is None:
        normalized["card_version"] = CHARACTER_CARD_VERSION
    elif isinstance(card_version, bool) or not isinstance(card_version, int) or card_version < 1:
        raise ValueError("card_version字段必须是大于等于1的整数")
    else:
        normalized["card_version"] = card_version
    return normalized


def validate_character_card_item(item: Any, index: int) -> list[str]:
    """Validate one native character-card JSON item without touching storage."""

    errors: list[str] = []
    label = f"第{index + 1}个角色"
    if not isinstance(item, dict):
        return [f"{label}必须是对象"]

    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}缺少name字段")

    for field in CHARACTER_CARD_TEXT_FIELDS:
        value = item.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"{label}的{field}字段必须是字符串")

    card_version = item.get("card_version")
    if card_version is not None and (isinstance(card_version, bool) or not isinstance(card_version, int) or card_version < 1):
        errors.append(f"{label}的card_version字段必须是大于等于1的整数")

    traits = item.get("traits")
    if traits is not None and not isinstance(traits, (list, str)):
        errors.append(f"{label}的traits字段必须是数组或JSON字符串")

    return errors


def validate_character_card_envelope(data: Any, supported_versions: list[str]) -> dict[str, Any]:
    """Validate a native character-card export envelope."""

    errors: list[str] = []
    warnings: list[str] = []
    version = ""
    statistics = {"characters": 0, "organizations": 0}

    if not isinstance(data, dict):
        return {
            "valid": False,
            "version": version,
            "statistics": statistics,
            "errors": ["导入数据格式错误：根节点必须是对象"],
            "warnings": warnings,
        }

    version = str(data.get("version") or "")
    if not version:
        errors.append("缺少版本信息")
    elif version not in supported_versions:
        warnings.append(f"版本不匹配: 导入文件版本为 {version}, 当前支持版本为 {', '.join(supported_versions)}")

    export_type = data.get("export_type", "")
    if export_type != "characters":
        errors.append(f"导出类型错误: 期望'characters'，实际'{export_type}'")

    raw_items = data.get("data")
    if raw_items is None:
        errors.append("缺少data字段")
    elif not isinstance(raw_items, list):
        errors.append("data字段必须是数组")
    else:
        statistics = {
            "characters": sum(1 for item in raw_items if isinstance(item, dict) and not item.get("is_organization", False)),
            "organizations": sum(1 for item in raw_items if isinstance(item, dict) and item.get("is_organization", False)),
        }
        for index, item in enumerate(raw_items):
            errors.extend(validate_character_card_item(item, index))

    if errors:
        statistics = {"characters": 0, "organizations": 0}

    return {
        "valid": len(errors) == 0,
        "version": version,
        "statistics": statistics,
        "errors": errors,
        "warnings": warnings,
    }
