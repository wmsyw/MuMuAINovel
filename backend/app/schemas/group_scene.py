"""Group scene authoring API schemas."""

# pyright: reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _strip_text(value: str | None) -> str:
    return str(value or "").strip()


class GroupSceneDraftRequest(BaseModel):
    """Create a bounded writing-only group scene draft."""

    title: str = Field(..., min_length=1, max_length=200)
    scenario: str = Field(..., min_length=1, max_length=4000)
    participant_character_ids: list[str] = Field(..., min_length=2, max_length=8)
    selected_voice_persona_id: str | None = Field(None, min_length=1)
    selected_lore_ids: list[str] = Field(default_factory=list, max_length=5)
    prompt_context: str = Field("", max_length=4000)
    draft_text: str | None = Field(None, max_length=12000, description="可选：前端/用户提供的初稿；为空时服务端生成边界草稿骨架")
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "scenario", "prompt_context", "draft_text", mode="before")
    @classmethod
    def _strip_fields(cls, value: str | None) -> str:
        return _strip_text(value)

    @field_validator("participant_character_ids", "selected_lore_ids")
    @classmethod
    def _dedupe_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            item_id = str(item or "").strip()
            if item_id and item_id not in seen:
                seen.add(item_id)
                normalized.append(item_id)
        return normalized

    @model_validator(mode="after")
    def _require_participants(self) -> "GroupSceneDraftRequest":
        if len(self.participant_character_ids) < 2:
            raise ValueError("群像场景至少需要两个项目角色")
        return self


class GroupSceneResponse(BaseModel):
    """Persisted project-scoped group scene artifact."""

    id: str
    project_id: str
    user_id: str
    title: str
    scenario: str
    participant_character_ids: list[str]
    selected_voice_persona_id: str | None = None
    selected_lore_ids: list[str]
    prompt_context: str
    draft_text: str
    prompt_trace: dict[str, Any]
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GroupSceneListResponse(BaseModel):
    """Paginated group scene list."""

    total: int
    items: list[GroupSceneResponse] = Field(default_factory=list)
