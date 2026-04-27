"""World-setting result API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field


WorldSettingResultStatus = Literal["pending", "accepted", "rejected", "superseded"]


class ProjectWorldSnapshot(BaseModel):
    """Active Project.world_* snapshot after a result operation."""

    project_id: str
    world_time_period: str | None = None
    world_location: str | None = None
    world_atmosphere: str | None = None
    world_rules: str | None = None


class WorldSettingResultResponse(BaseModel):
    """Reviewable world-setting generation/history result."""

    id: str
    project_id: str
    run_id: str | None = None
    status: WorldSettingResultStatus
    world_time_period: str | None = None
    world_location: str | None = None
    world_atmosphere: str | None = None
    world_rules: str | None = None
    prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    reasoning_intensity: str | None = None
    raw_result: dict[str, Any] | list[Any] | str | None = None
    source_type: str
    accepted_at: datetime | None = None
    accepted_by: str | None = None
    supersedes_result_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_result(cls, result: object) -> Self:
        """Validate a loaded ORM world-setting result into the API DTO."""

        return cls.model_validate(result)


class WorldSettingResultListResponse(BaseModel):
    """Paginated world-setting result list."""

    total: int
    items: list[WorldSettingResultResponse]


class WorldSettingResultOperationResponse(BaseModel):
    """World-setting review operation response."""

    changed: bool
    reason: str | None = None
    result: WorldSettingResultResponse
    previous_result: WorldSettingResultResponse | None = None
    active_world: ProjectWorldSnapshot


class WorldSettingRejectRequest(BaseModel):
    """Reject a pending world-setting result."""

    reason: str | None = Field(None, description="Reviewer rejection reason; retained for stable API symmetry")


class WorldSettingRollbackRequest(BaseModel):
    """Rollback an accepted world-setting result."""

    reason: str | None = Field(None, description="Reviewer rollback reason; retained for stable API symmetry")
