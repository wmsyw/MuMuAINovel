"""Narrator voice persona API schemas."""

# pyright: reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VoicePersonaScope = Literal["project", "session"]


def _strip_text(value: str | None) -> str:
    return str(value or "").strip()


class VoicePersonaCreate(BaseModel):
    """Create a narrator authoring voice profile. Client-supplied user_id is ignored."""

    name: str = Field(..., min_length=1, max_length=120)
    tone: str = Field("", max_length=2000)
    style: str = Field("", max_length=2000)
    point_of_view: str = Field("", max_length=1000)
    constraints: str = Field("", max_length=4000)
    session_id: str | None = Field(None, min_length=1, description="可选：将声音画像限定到一个创作会话")
    sort_order: int = 0
    enabled: bool = True
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "tone", "style", "point_of_view", "constraints", mode="before")
    @classmethod
    def _strip_fields(cls, value: str | None) -> str:
        return _strip_text(value)

    @model_validator(mode="after")
    def _require_authoring_content(self) -> "VoicePersonaCreate":
        if not any([self.tone, self.style, self.point_of_view, self.constraints]):
            raise ValueError("至少填写语气、文风、视角或约束中的一项")
        return self


class VoicePersonaUpdate(BaseModel):
    """Update a narrator voice profile. Omitted fields are left unchanged."""

    name: str | None = Field(None, min_length=1, max_length=120)
    tone: str | None = Field(None, max_length=2000)
    style: str | None = Field(None, max_length=2000)
    point_of_view: str | None = Field(None, max_length=1000)
    constraints: str | None = Field(None, max_length=4000)
    session_id: str | None = Field(None, min_length=1, description="传 null 可改回项目作用域")
    sort_order: int | None = None
    enabled: bool | None = None
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "tone", "style", "point_of_view", "constraints", mode="before")
    @classmethod
    def _strip_optional_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_text(value)


class VoicePersonaResponse(BaseModel):
    """Narrator voice profile response."""

    id: str
    project_id: str
    user_id: str
    session_id: str | None = None
    scope: VoicePersonaScope | str
    name: str
    tone: str
    style: str
    point_of_view: str
    constraints: str
    sort_order: int
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VoicePersonaListResponse(BaseModel):
    """Paginated narrator voice profile list."""

    total: int
    items: list[VoicePersonaResponse] = Field(default_factory=list)


class VoicePersonaPromptPreviewRequest(BaseModel):
    """Build a deterministic trace for applying a narrator voice profile."""

    persona_id: str = Field(..., min_length=1)
    session_id: str | None = Field(None, min_length=1)
    base_prompt: str = ""
    injection_enabled: bool = False
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="forbid")


class VoicePersonaPromptPreviewResponse(BaseModel):
    """Deterministic voice profile prompt trace preview."""

    project_id: str
    session_id: str | None = None
    trace: dict[str, Any]
    preview_prompt: str
