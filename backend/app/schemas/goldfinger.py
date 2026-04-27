"""金手指管理 Pydantic Schema"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


GOLDFINGER_PAYLOAD_VERSION = "goldfinger-card.v1"

GoldfingerStatus = Literal[
    "latent",
    "active",
    "sealed",
    "cooldown",
    "upgrading",
    "lost",
    "completed",
    "unknown",
]


class GoldfingerBase(BaseModel):
    """金手指基础字段。"""

    name: str = Field(..., min_length=1, max_length=200, description="名称")
    owner_character_id: str | None = Field(None, description="拥有者角色ID")
    owner_character_name: str | None = Field(None, max_length=200, description="拥有者角色名称快照")
    type: str | None = Field(None, max_length=50, description="类型：system/ability/artifact/bloodline等")
    status: GoldfingerStatus = Field("unknown", description="状态")
    summary: str | None = Field(None, description="概要")
    rules: Any | None = Field(None, description="规则(JSON)")
    tasks: Any | None = Field(None, description="任务(JSON)")
    rewards: Any | None = Field(None, description="奖励(JSON)")
    limits: Any | None = Field(None, description="限制(JSON)")
    trigger_conditions: Any | None = Field(None, description="触发条件(JSON)")
    cooldown: Any | None = Field(None, description="冷却信息(JSON)")
    aliases: Any | None = Field(None, description="别名(JSON)")
    metadata: dict[str, Any] | None = Field(None, description="元数据(JSON)")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="置信度")
    last_source_chapter_id: str | None = Field(None, description="最后来源章节ID")

    model_config = ConfigDict(extra="forbid")


class GoldfingerCreate(GoldfingerBase):
    """创建金手指请求。project_id 来自路径，不信任客户端传入。"""


class GoldfingerUpdate(BaseModel):
    """更新金手指请求。"""

    name: str | None = Field(None, min_length=1, max_length=200)
    owner_character_id: str | None = None
    owner_character_name: str | None = Field(None, max_length=200)
    type: str | None = Field(None, max_length=50)
    status: GoldfingerStatus | None = None
    summary: str | None = None
    rules: Any | None = None
    tasks: Any | None = None
    rewards: Any | None = None
    limits: Any | None = None
    trigger_conditions: Any | None = None
    cooldown: Any | None = None
    aliases: Any | None = None
    metadata: dict[str, Any] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    last_source_chapter_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class GoldfingerResponse(GoldfingerBase):
    """金手指响应。"""

    id: str
    project_id: str
    normalized_name: str
    created_by: str | None = None
    updated_by: str | None = None
    source: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, extra="allow")


class GoldfingerListResponse(BaseModel):
    """金手指列表响应。"""

    total: int
    items: list[GoldfingerResponse] = Field(default_factory=list)


class GoldfingerHistoryEventResponse(BaseModel):
    """金手指历史事件响应。"""

    id: str
    goldfinger_id: str
    project_id: str
    chapter_id: str | None = None
    event_type: str
    old_value: Any | None = None
    new_value: Any | None = None
    evidence_excerpt: str | None = None
    confidence: float | None = None
    source_type: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class GoldfingerHistoryListResponse(BaseModel):
    """历史事件列表响应。"""

    total: int
    items: list[GoldfingerHistoryEventResponse] = Field(default_factory=list)


class GoldfingerImportItem(BaseModel):
    """导入/导出中的单个金手指卡片。"""

    id: str | None = None
    name: str | None = None
    owner_character_id: str | None = None
    owner_character_name: str | None = None
    type: str | None = None
    status: str | None = "unknown"
    summary: str | None = None
    rules: Any | None = None
    tasks: Any | None = None
    rewards: Any | None = None
    limits: Any | None = None
    trigger_conditions: Any | None = None
    cooldown: Any | None = None
    aliases: Any | None = None
    metadata: dict[str, Any] | None = None
    confidence: float | None = None
    last_source_chapter_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(extra="allow")


class GoldfingerExportPayload(BaseModel):
    """金手指卡片导出载荷。"""

    version: str = GOLDFINGER_PAYLOAD_VERSION
    export_time: str
    export_type: str = "goldfingers"
    project_id: str
    count: int
    data: list[GoldfingerImportItem]


class GoldfingerImportPayload(BaseModel):
    """金手指卡片导入载荷。"""

    version: str
    export_time: str | None = None
    export_type: str | None = "goldfingers"
    project_id: str | None = None
    count: int | None = None
    data: list[GoldfingerImportItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class GoldfingerImportConflict(BaseModel):
    """导入冲突。"""

    index: int
    name: str | None = None
    normalized_name: str | None = None
    existing_id: str | None = None
    reason: str


class GoldfingerImportProblem(BaseModel):
    """导入校验问题。"""

    index: int | None = None
    name: str | None = None
    message: str


class GoldfingerImportDryRunResult(BaseModel):
    """导入 dry-run 结果。"""

    valid: bool
    version: str
    expected_version: str = GOLDFINGER_PAYLOAD_VERSION
    total: int
    creatable: int
    conflicts: list[GoldfingerImportConflict] = Field(default_factory=list)
    errors: list[GoldfingerImportProblem] = Field(default_factory=list)
    warnings: list[GoldfingerImportProblem] = Field(default_factory=list)
    would_create: list[dict[str, Any]] = Field(default_factory=list)
    statistics: dict[str, int] = Field(default_factory=dict)


class GoldfingerImportResult(BaseModel):
    """导入执行结果。"""

    success: bool
    message: str
    imported: int
    imported_ids: list[str] = Field(default_factory=list)
    dry_run: GoldfingerImportDryRunResult
    warnings: list[GoldfingerImportProblem] = Field(default_factory=list)
