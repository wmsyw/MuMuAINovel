"""Project-scoped local asset persistence models."""

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class ProjectAsset(Base):
    """A user-owned local image asset for a project workbench."""

    __tablename__ = "project_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="本地资源ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="服务端用户ID")
    asset_type = Column(String(30), nullable=False, comment="资源类型: avatar/background/sprite")
    display_name = Column(String(200), nullable=False, comment="展示名称")
    original_filename = Column(String(255), nullable=False, comment="原始上传文件名")
    storage_key = Column(String(500), nullable=False, unique=True, comment="相对存储路径")
    storage_filename = Column(String(255), nullable=False, comment="服务端生成文件名")
    mime_type = Column(String(100), nullable=False, comment="MIME类型")
    file_size = Column(Integer, nullable=False, comment="文件大小（字节）")
    content_hash = Column(String(64), nullable=False, index=True, comment="文件SHA256")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        CheckConstraint("asset_type IN ('avatar', 'background', 'sprite')", name="ck_project_assets_asset_type"),
        CheckConstraint("file_size >= 0", name="ck_project_assets_file_size_non_negative"),
        Index("idx_project_assets_project_user_type_created", "project_id", "user_id", "asset_type", "created_at"),
        Index("idx_project_assets_project_hash", "project_id", "content_hash"),
    )

    def __repr__(self) -> str:
        return f"<ProjectAsset(id={self.id}, project_id={self.project_id}, asset_type={self.asset_type})>"
