"""Timeline query API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TimelineEventType = Literal["relationship", "affiliation", "profession", "status"]
TimelineEventStatus = Literal["active", "ended", "superseded", "rolled_back"]


class TimelineQueryPoint(BaseModel):
    """Resolved story coordinate used for a timeline projection."""

    chapter_id: str | None = None
    chapter_number: int = Field(..., description="章节序号")
    chapter_order: int = Field(..., description="章节内/故事顺序")


class TimelineEventResponse(BaseModel):
    """Relationship/profession/organization timeline event response."""

    id: str
    project_id: str
    relationship_id: str | None = None
    organization_member_id: str | None = None
    character_id: str | None = None
    related_character_id: str | None = None
    organization_entity_id: str | None = None
    career_id: str | None = None
    event_type: TimelineEventType
    event_status: TimelineEventStatus
    relationship_name: str | None = None
    position: str | None = None
    rank: int | None = None
    career_stage: int | None = None
    story_time_label: str | None = None
    source_chapter_id: str | None = None
    source_chapter_order: int | None = None
    valid_from_chapter_id: str | None = None
    valid_from_chapter_order: int | None = None
    valid_to_chapter_id: str | None = None
    valid_to_chapter_order: int | None = None
    source_start_offset: int | None = None
    source_end_offset: int | None = None
    evidence_text: str | None = None
    confidence: float | None = None
    provenance_id: str | None = None
    supersedes_event_id: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TimelineStateResponse(BaseModel):
    """Current projected timeline state at a chapter/order point."""

    project_id: str
    point: TimelineQueryPoint
    relationships: list[TimelineEventResponse]
    affiliations: list[TimelineEventResponse]
    professions: list[TimelineEventResponse]


class TimelineHistoryResponse(BaseModel):
    """Timeline history response."""

    project_id: str
    event_type: TimelineEventType | None = None
    total: int
    items: list[TimelineEventResponse]
