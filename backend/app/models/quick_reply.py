"""Project-scoped quick reply / safe snippet persistence model."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


SAFE_SNIPPET_ACTION_TYPE = "safe_snippet"


class QuickReply(Base):
    """A project-owned quick action that can only emit a static safe snippet."""

    __tablename__ = "quick_replies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="快捷回复ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    label = Column(String(100), nullable=False, comment="按钮标签")
    action_type = Column(String(30), nullable=False, default=SAFE_SNIPPET_ACTION_TYPE, server_default=SAFE_SNIPPET_ACTION_TYPE, comment="动作类型，仅允许safe_snippet")
    snippet = Column(Text, nullable=False, comment="安全静态片段内容")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0", comment="显示顺序，数值越小越靠前")
    enabled = Column(Boolean, nullable=False, default=True, server_default="1", comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        CheckConstraint("action_type = 'safe_snippet'", name="ck_quick_replies_action_type_safe_snippet"),
        Index("idx_quick_replies_project_user_order", "project_id", "user_id", "sort_order"),
        Index("idx_quick_replies_project_enabled", "project_id", "enabled"),
    )

    def __repr__(self) -> str:
        return f"<QuickReply(id={self.id}, project_id={self.project_id}, action_type={self.action_type})>"
