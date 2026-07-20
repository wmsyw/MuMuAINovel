"""Reusable inspiration generation templates."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class InspirationTemplate(Base):
    """System or user-owned parameterized inspiration prompt."""

    __tablename__ = "inspiration_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=True, index=True, comment="用户ID；系统模板为空")
    name = Column(String(100), nullable=False, comment="模板名称")
    category = Column(String(50), nullable=False, comment="platform/genre/theme")
    tags = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list, comment="标签数组")
    prompt_template = Column(Text, nullable=False, comment="参数化提示词模板")
    platform = Column(String(50), nullable=True, index=True, comment="目标平台")
    is_system = Column(Boolean, nullable=False, default=False, server_default="0", comment="系统预置模板")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("ix_inspiration_templates_category_system", "category", "is_system"),
    )

    def __repr__(self) -> str:
        return f"<InspirationTemplate(id={self.id}, name={self.name}, platform={self.platform})>"
