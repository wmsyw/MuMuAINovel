"""金手指（核心能力/系统）数据模型"""
from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.sql import func
from app.database import Base
import uuid


GOLDFINGER_STATUSES = (
    "latent",
    "active",
    "sealed",
    "cooldown",
    "upgrading",
    "lost",
    "completed",
    "unknown",
)


class Goldfinger(Base):
    """项目内规范化金手指/系统/能力表。"""
    __tablename__ = "goldfingers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="金手指ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    name = Column(String(200), nullable=False, comment="名称")
    normalized_name = Column(String(200), nullable=False, comment="规范化名称")
    owner_character_id = Column(String(36), ForeignKey("characters.id", ondelete="SET NULL"), index=True, comment="拥有者角色ID")
    owner_character_name = Column(String(200), comment="拥有者角色名称快照")
    type = Column(String(50), comment="类型：system/ability/artifact/bloodline等")
    status = Column(String(20), default="unknown", server_default="unknown", nullable=False, comment="状态")
    summary = Column(Text, comment="概要")

    rules = Column(JSON, comment="规则(JSON)")
    tasks = Column(JSON, comment="任务(JSON)")
    rewards = Column(JSON, comment="奖励(JSON)")
    limits = Column(JSON, comment="限制(JSON)")
    trigger_conditions = Column(JSON, comment="触发条件(JSON)")
    cooldown = Column(JSON, comment="冷却信息(JSON)")
    aliases = Column(JSON, comment="别名(JSON)")
    goldfinger_metadata = Column("metadata", JSON, comment="元数据(JSON)")

    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    created_by = Column(String(100), ForeignKey("users.user_id", ondelete="SET NULL"), index=True, comment="创建用户/系统")
    updated_by = Column(String(100), ForeignKey("users.user_id", ondelete="SET NULL"), index=True, comment="更新用户/系统")
    source = Column(String(50), default="manual", server_default="manual", nullable=False, comment="来源：manual/ai/extraction/imported")
    confidence = Column(Float, comment="置信度")
    last_source_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="最后来源章节ID")

    __table_args__ = (
        CheckConstraint(
            "status IN ('latent', 'active', 'sealed', 'cooldown', 'upgrading', 'lost', 'completed', 'unknown')",
            name="ck_goldfingers_status",
        ),
        Index("idx_goldfingers_project_name", "project_id", "normalized_name"),
        Index("idx_goldfingers_project_status", "project_id", "status"),
        Index("idx_goldfingers_owner_status", "owner_character_id", "status"),
    )

    def __repr__(self):
        return f"<Goldfinger(id={self.id}, name={self.name}, status={self.status})>"


class GoldfingerHistoryEvent(Base):
    """金手指状态/规则/归属变化历史事件。"""
    __tablename__ = "goldfinger_history_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="金手指历史事件ID")
    goldfinger_id = Column(String(36), ForeignKey("goldfingers.id", ondelete="CASCADE"), nullable=False, index=True, comment="金手指ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="章节ID")
    event_type = Column(String(50), nullable=False, comment="事件类型：status/rule/task/reward/owner等")
    old_value = Column(JSON, comment="旧值(JSON)")
    new_value = Column(JSON, comment="新值(JSON)")
    evidence_excerpt = Column(Text, comment="证据摘录")
    confidence = Column(Float, comment="置信度")
    source_type = Column(String(50), comment="来源类型：manual/extraction/imported")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_goldfinger_history_goldfinger_created", "goldfinger_id", "created_at"),
        Index("idx_goldfinger_history_project_type", "project_id", "event_type"),
    )

    def __repr__(self):
        return f"<GoldfingerHistoryEvent(id={self.id}, goldfinger_id={self.goldfinger_id}, event_type={self.event_type})>"
