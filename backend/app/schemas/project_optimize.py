# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from pydantic import BaseModel, Field


SOFT_TEXT_MAX_LENGTH = 5000


class OptimizableFieldMeta(TypedDict):
    label: str
    max_length: int | None


OPTIMIZABLE_FIELDS: dict[str, OptimizableFieldMeta] = {
    "title": {"label": "项目标题", "max_length": 200},
    "description": {"label": "项目简介", "max_length": None},
    "theme": {"label": "主题", "max_length": None},
    "genre": {"label": "小说类型", "max_length": 50},
    "world_time_period": {"label": "时间背景", "max_length": None},
    "world_location": {"label": "地理位置", "max_length": None},
    "world_atmosphere": {"label": "氛围基调", "max_length": None},
    "world_rules": {"label": "世界规则", "max_length": None},
    "narrative_perspective": {"label": "叙事视角", "max_length": 50},
}


class ProjectOptimizeRequest(BaseModel):
    requirement: str | None = Field(None, description="优化要求")
    conversation_history: list[object] | None = Field(None, description="对话历史")
    current_draft: dict[str, object] | None = Field(None, description="当前草稿")


class FieldSuggestion(BaseModel):
    value: str = Field(..., description="建议值")
    reason: str = Field(..., description="建议理由")


class ProjectOptimizeResult(BaseModel):
    fields: dict[str, FieldSuggestion] = Field(default_factory=dict, description="字段建议")
    reply: str = Field(..., description="回复内容")


def filter_and_validate_suggestions(raw: Mapping[str, object] | None) -> dict[str, str]:
    filtered: dict[str, str] = {}
    if raw is None:
        return filtered

    for field_name, value in raw.items():
        field_meta = OPTIMIZABLE_FIELDS.get(field_name)
        if field_meta is None or value is None:
            continue

        if isinstance(value, str):
            normalized_value = value
        else:
            normalized_value = str(value)

        if normalized_value == "":
            continue

        max_length = field_meta["max_length"] or SOFT_TEXT_MAX_LENGTH
        if len(normalized_value) > max_length:
            normalized_value = normalized_value[:max_length]

        if normalized_value == "":
            continue

        filtered[field_name] = normalized_value

    return filtered
