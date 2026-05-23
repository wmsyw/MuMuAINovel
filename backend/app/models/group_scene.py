"""Project-scoped group scene authoring artifacts."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


GROUP_SCENE_STATUS_DRAFT = "draft"
GROUP_SCENE_STATUS_ARCHIVED = "archived"


class GroupScene(Base):
    """Writing-only multi-character scene draft; not a chat room."""

    __tablename__ = "group_scenes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="群像场景ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    title = Column(String(200), nullable=False, comment="场景标题")
    scenario = Column(Text, nullable=False, comment="场景目标/背景")
    participant_character_ids = Column(JSON, nullable=False, default=list, comment="参与角色ID列表")
    selected_voice_persona_id = Column(String(36), ForeignKey("voice_personas.id", ondelete="SET NULL"), nullable=True, index=True, comment="选用旁白声音画像ID")
    selected_lore_ids = Column(JSON, nullable=False, default=list, comment="选用Lorebook条目ID列表")
    prompt_context = Column(Text, nullable=False, default="", server_default="", comment="作者选择的额外提示上下文")
    draft_text = Column(Text, nullable=False, default="", server_default="", comment="场景对话草稿")
    prompt_trace = Column(JSON, nullable=False, default=dict, comment="确定性Prompt上下文追踪")
    status = Column(String(20), nullable=False, default=GROUP_SCENE_STATUS_DRAFT, server_default=GROUP_SCENE_STATUS_DRAFT, comment="状态: draft/archived")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'archived')", name="ck_group_scenes_status"),
        Index("idx_group_scenes_project_user_updated", "project_id", "user_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<GroupScene(id={self.id}, project_id={self.project_id}, status={self.status})>"
