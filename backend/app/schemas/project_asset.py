"""Project local asset API schemas."""

# pyright: reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ProjectAssetType = Literal["avatar", "background", "sprite"]


class ProjectAssetResponse(BaseModel):
    """Local project asset metadata response."""

    id: str
    project_id: str
    user_id: str
    asset_type: ProjectAssetType | str
    display_name: str
    original_filename: str
    storage_filename: str
    mime_type: str
    file_size: int
    content_hash: str
    file_url: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProjectAssetListResponse(BaseModel):
    """Paginated local project asset list."""

    total: int
    items: list[ProjectAssetResponse] = Field(default_factory=list)
