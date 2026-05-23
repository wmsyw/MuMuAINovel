"""Lorebook API schemas."""

# pyright: reportExplicitAny=false, reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_keys(keys: list[str] | None) -> list[str]:
    if not keys:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for key in keys:
        stripped = str(key).strip()
        folded = stripped.casefold()
        if stripped and folded not in seen:
            normalized.append(stripped)
            seen.add(folded)
    return normalized


class LorebookEntryCreate(BaseModel):
    """Create a lorebook entry. Client-supplied user_id is ignored by the API."""

    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    activation_keys: list[str] = Field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    source_type: str = Field("manual", min_length=1, max_length=50)
    metadata: dict[str, Any] | None = None
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="allow")

    @field_validator("title", "content", "source_type")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("activation_keys")
    @classmethod
    def _normalize_activation_keys(cls, value: list[str]) -> list[str]:
        return _normalize_keys(value)


class LorebookEntryUpdate(BaseModel):
    """Update a lorebook entry. Omitted fields are left unchanged."""

    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = Field(None, min_length=1)
    activation_keys: list[str] | None = None
    priority: int | None = None
    enabled: bool | None = None
    source_type: str | None = Field(None, min_length=1, max_length=50)
    metadata: dict[str, Any] | None = None
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="allow")

    @field_validator("title", "content", "source_type")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("activation_keys")
    @classmethod
    def _normalize_activation_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_keys(value)


class LorebookEntryResponse(BaseModel):
    """Lorebook entry response."""

    id: str
    project_id: str
    user_id: str
    title: str
    content: str
    activation_keys: list[str] = Field(default_factory=list)
    priority: int
    enabled: bool
    source_type: str
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LorebookEntryListResponse(BaseModel):
    """Paginated lorebook entry list."""

    total: int
    items: list[LorebookEntryResponse] = Field(default_factory=list)


class LorebookSelectionRequest(BaseModel):
    """Pure selection preview request; does not mutate generation prompts."""

    activation_text: str = Field("", description="Text scanned for activation keys")
    max_chars: int | None = Field(None, ge=1, description="Maximum selected lore characters")
    max_tokens: int | None = Field(None, ge=1, description="Approximate token budget converted to characters")
    chars_per_token: int = Field(4, ge=1, le=20, description="Character estimate for one token")


class LorebookSelectedEntryResponse(BaseModel):
    """A selected lorebook entry with deterministic trimming metadata."""

    id: str
    title: str
    priority: int
    order: int | None = None
    source_type: str | None = None
    entry_source_type: str | None = None
    matched_keys: list[str]
    content: str
    original_content_length: int
    selected_content_length: int
    trimmed: bool


class LorebookSelectionResponse(BaseModel):
    """Selection preview response."""

    total_candidates: int
    selected_count: int
    chars_used: int
    budget_chars: int | None = None
    items: list[LorebookSelectedEntryResponse] = Field(default_factory=list)


class LorebookPromptTraceBudget(BaseModel):
    """Deterministic budget estimate for prompt trace output."""

    chars_used: int
    budget_chars: int | None = None
    estimated_tokens: int
    chars_per_token: int


class LorebookPromptTraceItem(BaseModel):
    """One lorebook item in prompt trace order."""

    order: int
    id: str
    title: str
    source_type: str
    entry_source_type: str
    priority: int
    matched_keys: list[str]
    content: str
    original_content_length: int
    selected_content_length: int
    trimmed: bool


class LorebookPromptTrace(BaseModel):
    """Trace payload consumed by preview UI and future prompt injection."""

    source_type: str
    selected_lore_ids: list[str]
    total_candidates: int
    selected_count: int
    budget_estimate: LorebookPromptTraceBudget
    items: list[LorebookPromptTraceItem] = Field(default_factory=list)
    final_preview_text: str


class LorebookPromptPreviewResponse(BaseModel):
    """Lorebook prompt preview response; never mutates generation by itself."""

    project_id: str
    trace: LorebookPromptTrace
