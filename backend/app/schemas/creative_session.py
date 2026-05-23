"""创作会话 Pydantic Schema。"""

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CreativeSessionStatus = Literal["active", "archived"]
CreativeSessionRole = Literal["user", "assistant", "system", "note"]


class CreativeSessionCreate(BaseModel):
    """创建创作会话请求。user_id 如被客户端传入也会被忽略。"""

    title: str = Field("未命名创作会话", min_length=1, max_length=200)
    metadata: dict[str, Any] | None = None
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="allow")


class CreativeSessionUpdate(BaseModel):
    """更新创作会话请求。"""

    title: str | None = Field(None, min_length=1, max_length=200)
    status: CreativeSessionStatus | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class CreativeSessionMessageCreate(BaseModel):
    """追加会话消息请求。user_id 如被客户端传入也会被忽略。"""

    role: CreativeSessionRole = "user"
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] | None = None
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="allow")


class CreativeSessionMessageResponse(BaseModel):
    """创作会话消息响应。"""

    id: str
    session_id: str
    project_id: str
    user_id: str
    role: str
    content: str
    position: int
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None


class CreativeSessionResponse(BaseModel):
    """创作会话响应。"""

    id: str
    project_id: str
    user_id: str
    title: str
    status: str
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreativeSessionDetailResponse(CreativeSessionResponse):
    """包含消息的创作会话响应。"""

    messages: list[CreativeSessionMessageResponse] = Field(default_factory=list)


class CreativeSessionListResponse(BaseModel):
    """创作会话列表响应。"""

    total: int
    items: list[CreativeSessionResponse] = Field(default_factory=list)


class CreativeSessionSearchResult(BaseModel):
    """创作会话搜索结果。"""

    session_id: str
    session_title: str
    message_id: str
    project_id: str
    user_id: str
    role: str
    content: str
    position: int
    created_at: datetime | None = None


class CreativeSessionSearchResponse(BaseModel):
    """创作会话搜索响应。"""

    query: str
    total: int
    items: list[CreativeSessionSearchResult] = Field(default_factory=list)
