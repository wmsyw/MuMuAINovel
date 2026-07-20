"""Schemas for reusable and project-specific world-setting structures."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class WorldSettingFieldDefinition(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    type: Literal["text", "textarea", "list"] = "textarea"
    required: bool = False


class WorldSettingTemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    fields: dict[str, WorldSettingFieldDefinition]
    example_data: dict[str, Any] = Field(default_factory=dict)
    is_system: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorldSettingTemplateListResponse(BaseModel):
    total: int
    items: list[WorldSettingTemplateResponse]


class WorldSettingApplyTemplateRequest(BaseModel):
    project_id: str
    template_id: str
    values: dict[str, Any] = Field(default_factory=dict)
    custom_fields: dict[str, WorldSettingFieldDefinition] = Field(default_factory=dict)

    @field_validator("values")
    @classmethod
    def validate_value_count(cls, values: dict[str, Any]) -> dict[str, Any]:
        if len(values) > 100:
            raise ValueError("世界设定字段不能超过100个")
        return values


class ProjectWorldSettingData(BaseModel):
    template_id: str | None = None
    template_name: str | None = None
    fields: dict[str, WorldSettingFieldDefinition] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)


class WorldSettingApplyTemplateResponse(BaseModel):
    project_id: str
    template: WorldSettingTemplateResponse
    world_setting_data: ProjectWorldSettingData
