"""Lorebook / world-info persistence models."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


class LorebookEntry(Base):
    """Project-scoped lorebook entry, independent from world-setting snapshots."""

    __tablename__ = "lorebook_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="Lorebook条目ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    title = Column(String(200), nullable=False, comment="条目标题")
    content = Column(Text, nullable=False, comment="条目内容")
    activation_keys = Column(JSON, nullable=False, default=list, comment="激活关键词列表")
    priority = Column(Integer, nullable=False, default=0, server_default="0", comment="选择优先级，数值越高越靠前")
    enabled = Column(Boolean, nullable=False, default=True, server_default="1", comment="是否启用")
    source_type = Column(String(50), nullable=False, default="manual", server_default="manual", comment="来源类型：manual/imported/derived")
    entry_metadata = Column("metadata", JSON, comment="条目元数据(JSON)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_lorebook_entries_project_user_priority", "project_id", "user_id", "priority"),
        Index("idx_lorebook_entries_project_enabled", "project_id", "enabled"),
    )

    def __repr__(self) -> str:
        return f"<LorebookEntry(id={self.id}, project_id={self.project_id}, enabled={self.enabled})>"
