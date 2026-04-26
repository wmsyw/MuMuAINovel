"""Extraction review API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ExtractionRunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
ExtractionCandidateStatus = Literal["pending", "accepted", "rejected", "merged", "superseded"]
ExtractionCandidateType = Literal[
    "character",
    "organization",
    "profession",
    "relationship",
    "organization_affiliation",
    "profession_assignment",
    "world_fact",
    "character_state",
]
CanonicalTargetType = Literal["character", "organization", "career"]


class ExtractionRunResponse(BaseModel):
    """Extraction run response."""

    id: str
    project_id: str
    chapter_id: str | None = None
    trigger_source: str
    pipeline_version: str
    schema_version: str
    prompt_hash: str | None = None
    content_hash: str
    status: ExtractionRunStatus
    provider: str | None = None
    model: str | None = None
    reasoning_intensity: str | None = None
    raw_response: dict[str, Any] | list[Any] | str | None = None
    run_metadata: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExtractionRunListResponse(BaseModel):
    """Paginated extraction run list."""

    total: int
    items: list[ExtractionRunResponse]


class ManualReextractProjectRequest(BaseModel):
    """Manual project-wide re-extraction request."""

    project_id: str = Field(..., description="Project to re-extract")


class ManualReextractChapterRequest(BaseModel):
    """Manual chapter re-extraction request."""

    project_id: str = Field(..., description="Project that owns the chapter")
    chapter_id: str = Field(..., description="Chapter to re-extract")


class ManualReextractRangeRequest(BaseModel):
    """Manual chapter range re-extraction request."""

    project_id: str = Field(..., description="Project to re-extract")
    start_chapter_number: int = Field(..., ge=1, description="Inclusive start chapter number")
    end_chapter_number: int = Field(..., ge=1, description="Inclusive end chapter number")


class ManualReextractResponse(BaseModel):
    """Manual re-extraction operation result."""

    project_id: str
    scope: Literal["project", "chapter", "range"]
    total_runs: int
    runs: list[ExtractionRunResponse]


class ExtractionCandidateResponse(BaseModel):
    """Extraction candidate response."""

    id: str
    run_id: str
    project_id: str
    user_id: str
    source_chapter_id: str | None = None
    source_chapter_start_id: str | None = None
    source_chapter_end_id: str | None = None
    candidate_type: ExtractionCandidateType
    trigger_type: str
    source_hash: str
    provider: str | None = None
    model: str | None = None
    reasoning_intensity: str | None = None
    display_name: str | None = None
    normalized_name: str | None = None
    canonical_target_type: CanonicalTargetType | None = None
    canonical_target_id: str | None = None
    status: ExtractionCandidateStatus
    confidence: float
    evidence_text: str
    source_start_offset: int
    source_end_offset: int
    source_chapter_number: int | None = None
    source_chapter_order: int | None = None
    valid_from_chapter_id: str | None = None
    valid_from_chapter_order: int | None = None
    valid_to_chapter_id: str | None = None
    valid_to_chapter_order: int | None = None
    story_time_label: str | None = None
    payload: dict[str, Any]
    raw_payload: dict[str, Any] | list[Any] | str | None = None
    merge_target_type: str | None = None
    merge_target_id: str | None = None
    reviewer_user_id: str | None = None
    reviewed_at: datetime | None = None
    accepted_at: datetime | None = None
    rejection_reason: str | None = None
    supersedes_candidate_id: str | None = None
    rollback_of_candidate_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExtractionCandidateListResponse(BaseModel):
    """Paginated extraction candidate list."""

    total: int
    items: list[ExtractionCandidateResponse]


class CandidateAcceptRequest(BaseModel):
    """Accept a candidate, optionally targeting an existing canonical row."""

    target_type: CanonicalTargetType | None = Field(None, description="Existing canonical target type")
    target_id: str | None = Field(None, description="Existing canonical target ID")
    override: bool = Field(False, description="Allow resolving otherwise ambiguous/conflicting claims")
    supersedes_candidate_id: str | None = Field(None, description="Candidate superseded by this acceptance")


class CandidateMergeRequest(BaseModel):
    """Merge a candidate into an existing canonical row."""

    target_type: CanonicalTargetType = Field(..., description="Existing canonical target type")
    target_id: str = Field(..., description="Existing canonical target ID")
    override: bool = Field(False, description="Allow resolving otherwise ambiguous/conflicting claims")


class CandidateRejectRequest(BaseModel):
    """Reject a pending candidate."""

    reason: str | None = Field(None, description="Reviewer rejection reason")


class CandidateRollbackRequest(BaseModel):
    """Rollback accepted/merged candidate side effects."""

    reason: str | None = Field(None, description="Reviewer rollback reason")


class CandidateReviewResponse(BaseModel):
    """Candidate review operation result."""

    changed: bool
    reason: str | None = None
    candidate: ExtractionCandidateResponse


class StructuredAPIError(BaseModel):
    """Structured API error payload used in HTTPException.detail."""

    code: str
    message: str
