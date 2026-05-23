"""创作会话数据模型。"""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportImportCycles=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


class CreativeSession(Base):
    """项目内创作会话。"""

    __tablename__ = "creative_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="会话ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    title = Column(String(200), nullable=False, default="未命名创作会话", comment="会话标题")
    status = Column(String(20), nullable=False, default="active", comment="状态: active/archived")
    session_metadata = Column("metadata", JSON, comment="会话元数据(JSON)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_creative_sessions_status"),
        Index("idx_creative_sessions_project_user_updated", "project_id", "user_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<CreativeSession(id={self.id}, project_id={self.project_id}, status={self.status})>"


class CreativeSessionMessage(Base):
    """创作会话消息。"""

    __tablename__ = "creative_session_messages"

    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="消息ID")
    session_id = Column(String(36), ForeignKey("creative_sessions.id", ondelete="CASCADE"), nullable=False, index=True, comment="会话ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    role = Column(String(30), nullable=False, comment="消息角色: user/assistant/system/note")
    content = Column(Text, nullable=False, comment="消息内容")
    position = Column(Integer, nullable=False, default=0, comment="会话内顺序")
    message_metadata = Column("metadata", JSON, comment="消息元数据(JSON)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system', 'note')", name="ck_creative_session_messages_role"),
        Index("idx_creative_session_messages_session_position", "session_id", "position"),
        Index("idx_creative_session_messages_project_user_created", "project_id", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<CreativeSessionMessage(id={self.id}, session_id={self.session_id}, role={self.role})>"
