"""Reusable world-setting template model."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, JSON, String
from sqlalchemy.sql import func

from app.database import Base


class WorldSettingTemplate(Base):
    """System or user-owned dynamic world-setting field definitions."""

    __tablename__ = "world_setting_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=True, index=True, comment="空值表示系统模板")
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    field_definitions = Column("fields", JSON, nullable=False)
    example_data = Column(JSON, nullable=True)
    is_system = Column(Boolean, default=False, server_default="0", nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_world_setting_templates_category_system", "category", "is_system"),
    )
