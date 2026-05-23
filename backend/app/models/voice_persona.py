"""Project/session scoped narrator voice profile persistence model."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


VOICE_PERSONA_PROJECT_SCOPE = "project"
VOICE_PERSONA_SESSION_SCOPE = "session"


class VoicePersona(Base):
    """Narrator authoring voice profile for prompt guidance only."""

    __tablename__ = "voice_personas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="旁白声音画像ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    session_id = Column(String(36), ForeignKey("creative_sessions.id", ondelete="CASCADE"), nullable=True, index=True, comment="可选创作会话ID")
    scope = Column(String(20), nullable=False, default=VOICE_PERSONA_PROJECT_SCOPE, server_default=VOICE_PERSONA_PROJECT_SCOPE, comment="作用域: project/session")
    name = Column(String(120), nullable=False, comment="声音画像名称")
    tone = Column(Text, nullable=False, comment="叙述语气")
    style = Column(Text, nullable=False, comment="文风特征")
    point_of_view = Column(Text, nullable=False, comment="叙事视角")
    constraints = Column(Text, nullable=False, comment="写作约束")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0", comment="显示顺序，数值越小越靠前")
    enabled = Column(Boolean, nullable=False, default=True, server_default="1", comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        CheckConstraint("scope IN ('project', 'session')", name="ck_voice_personas_scope"),
        CheckConstraint(
            "(scope = 'project' AND session_id IS NULL) OR (scope = 'session' AND session_id IS NOT NULL)",
            name="ck_voice_personas_scope_session",
        ),
        Index("idx_voice_personas_project_user_scope_order", "project_id", "user_id", "scope", "sort_order"),
        Index("idx_voice_personas_session_user_order", "session_id", "user_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<VoicePersona(id={self.id}, project_id={self.project_id}, scope={self.scope})>"
