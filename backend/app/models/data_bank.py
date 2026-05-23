"""Project-scoped Data Bank persistence models."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


class DataBankItem(Base):
    """A user-owned, project-scoped local text source for RAG retrieval."""

    __tablename__ = "data_bank_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="Data Bank条目ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    title = Column(String(200), nullable=False, comment="条目标题")
    source_type = Column(String(30), nullable=False, default="snippet", comment="来源类型: snippet/upload")
    filename = Column(String(255), nullable=True, comment="上传文件名")
    content_type = Column(String(100), nullable=True, comment="上传MIME类型")
    content_hash = Column(String(64), nullable=False, index=True, comment="原文SHA256")
    text_content = Column(Text, nullable=False, comment="本地原文内容")
    chunk_count = Column(Integer, nullable=False, default=0, comment="切片数量")
    item_metadata = Column("metadata", JSON, comment="条目元数据(JSON)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        CheckConstraint("source_type IN ('snippet', 'upload')", name="ck_data_bank_items_source_type"),
        Index("idx_data_bank_items_project_user_created", "project_id", "user_id", "created_at"),
        Index("idx_data_bank_items_project_hash", "project_id", "content_hash"),
    )

    def __repr__(self) -> str:
        return f"<DataBankItem(id={self.id}, project_id={self.project_id}, source_type={self.source_type})>"


class DataBankChunk(Base):
    """Deterministic text chunk derived from a Data Bank item."""

    __tablename__ = "data_bank_chunks"

    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="Data Bank切片ID")
    item_id = Column(String(36), ForeignKey("data_bank_items.id", ondelete="CASCADE"), nullable=False, index=True, comment="条目ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    chunk_index = Column(Integer, nullable=False, comment="条目内切片序号")
    content = Column(Text, nullable=False, comment="切片文本")
    char_start = Column(Integer, nullable=False, comment="原文起始字符偏移")
    char_end = Column(Integer, nullable=False, comment="原文结束字符偏移")
    content_hash = Column(String(64), nullable=False, index=True, comment="切片SHA256")
    chunk_metadata = Column("metadata", JSON, comment="切片元数据(JSON)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_data_bank_chunks_project_user_item", "project_id", "user_id", "item_id"),
        Index("idx_data_bank_chunks_item_index", "item_id", "chunk_index", unique=True),
    )

    def __repr__(self) -> str:
        return f"<DataBankChunk(id={self.id}, item_id={self.item_id}, index={self.chunk_index})>"
