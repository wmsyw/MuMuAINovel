"""Quick reply API schemas."""

# pyright: reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.quick_reply import SAFE_SNIPPET_ACTION_TYPE
from app.schemas.creative_session import CreativeSessionMessageResponse


QuickReplyActionType = Literal["safe_snippet"]


class QuickReplyCreate(BaseModel):
    """Create a quick reply. Client-supplied user_id is ignored by the API."""

    label: str = Field(..., min_length=1, max_length=100)
    action_type: QuickReplyActionType = SAFE_SNIPPET_ACTION_TYPE
    snippet: str = Field(..., min_length=1, max_length=4000)
    sort_order: int = 0
    enabled: bool = True
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="forbid")

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

class QuickReplyUpdate(BaseModel):
    """Update a quick reply. Omitted fields are left unchanged."""

    label: str | None = Field(None, min_length=1, max_length=100)
    action_type: QuickReplyActionType | None = None
    snippet: str | None = Field(None, min_length=1, max_length=4000)
    sort_order: int | None = None
    enabled: bool | None = None
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="forbid")

    @field_validator("label")
    @classmethod
    def _strip_optional_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

class QuickReplyResponse(BaseModel):
    """Quick reply response."""

    id: str
    project_id: str
    user_id: str
    label: str
    action_type: str
    snippet: str
    sort_order: int
    enabled: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QuickReplyListResponse(BaseModel):
    """Paginated quick reply list."""

    total: int
    items: list[QuickReplyResponse] = Field(default_factory=list)


class QuickReplyApplyRequest(BaseModel):
    """Apply a safe snippet to an existing creative session."""

    session_id: str = Field(..., min_length=1)
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="forbid")


class QuickReplyApplyResponse(BaseModel):
    """Explicit safe-snippet application trace."""

    quick_reply: QuickReplyResponse
    source_type: str
    trace_label: str
    action_type: str
    applied_content: str
    prompt_mutation: bool
    boundary_decision: str
    emitted_message: CreativeSessionMessageResponse
