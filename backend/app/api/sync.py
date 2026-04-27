"""Chapter fact synchronization and pending review API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import verify_project_access
from app.database import get_db
from app.models.relationship import ExtractionCandidate, ExtractionRun
from app.services.candidate_merge_service import CandidateMergeService
from app.services.chapter_fact_sync_service import (
    CHAPTER_FACT_SYNC_PIPELINE_VERSION,
    CHAPTER_FACT_SYNC_SCHEMA_VERSION,
    ChapterFactSyncService,
)
from app.services.goldfinger_sync_service import GoldfingerSyncService


router = APIRouter(prefix="/sync", tags=["章节事实同步"])


class SyncRunResponse(BaseModel):
    id: str
    project_id: str
    chapter_id: str | None = None
    trigger_source: str
    pipeline_version: str
    schema_version: str
    prompt_hash: str | None = None
    content_hash: str
    status: str
    raw_response: dict[str, Any] | list[Any] | str | None = None
    run_metadata: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SyncRunListResponse(BaseModel):
    total: int
    items: list[SyncRunResponse]


class SyncCandidateResponse(BaseModel):
    id: str
    run_id: str
    project_id: str
    user_id: str
    source_chapter_id: str | None = None
    candidate_type: str
    trigger_type: str
    source_hash: str
    display_name: str | None = None
    normalized_name: str | None = None
    canonical_target_type: str | None = None
    canonical_target_id: str | None = None
    status: str
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
    review_required_reason: str | None = None
    rejection_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SyncCandidateListResponse(BaseModel):
    total: int
    items: list[SyncCandidateResponse]


class SyncCandidateApproveRequest(BaseModel):
    target_type: str | None = Field(None, description="Optional existing canonical target type")
    target_id: str | None = Field(None, description="Optional existing canonical target ID")
    override: bool = Field(False, description="Allow ambiguous/conflicting supported merge claims")
    supersedes_candidate_id: str | None = Field(None, description="Candidate superseded by this approval")


class SyncCandidateRejectRequest(BaseModel):
    reason: str | None = Field(None, description="Reviewer rejection reason")


class SyncCandidateReviewResponse(BaseModel):
    changed: bool
    reason: str | None = None
    candidate: SyncCandidateResponse


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _structured_error(status_code: int, *, code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _get_run_for_user(run_id: str, user_id: str, db: AsyncSession) -> ExtractionRun:
    result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None or run.pipeline_version != CHAPTER_FACT_SYNC_PIPELINE_VERSION:
        raise HTTPException(status_code=404, detail="同步运行不存在")
    _ = await verify_project_access(run.project_id, user_id, db)
    return run


async def _get_candidate_for_user(candidate_id: str, user_id: str, db: AsyncSession) -> ExtractionCandidate:
    result = await db.execute(select(ExtractionCandidate).where(ExtractionCandidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="同步候选不存在")
    _ = await verify_project_access(candidate.project_id, user_id, db)
    return candidate


async def _candidate_response(candidate_id: str, db: AsyncSession) -> SyncCandidateResponse:
    result = await db.execute(select(ExtractionCandidate).where(ExtractionCandidate.id == candidate_id))
    return SyncCandidateResponse.model_validate(result.scalar_one())


def _sync_schema_version(entity_type: str) -> str:
    return f"{CHAPTER_FACT_SYNC_SCHEMA_VERSION}:{entity_type}"


@router.get("/project/{project_id}/runs", response_model=SyncRunListResponse, summary="列出章节事实同步运行")
async def list_project_sync_runs(
    project_id: str,
    request: Request,
    status: str | None = Query(None, description="运行状态"),
    entity_type: str | None = Query(None, description="事实类型：relationship/goldfinger"),
    chapter_id: str | None = Query(None, description="章节ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SyncRunListResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(project_id, user_id, db)

    filters = [
        ExtractionRun.project_id == project_id,
        ExtractionRun.pipeline_version == CHAPTER_FACT_SYNC_PIPELINE_VERSION,
    ]
    if status is not None:
        filters.append(ExtractionRun.status == status)
    if entity_type is not None:
        filters.append(ExtractionRun.schema_version == _sync_schema_version(entity_type.strip().lower()))
    if chapter_id is not None:
        filters.append(ExtractionRun.chapter_id == chapter_id)

    count_result = await db.execute(select(func.count(ExtractionRun.id)).where(*filters))
    result = await db.execute(
        select(ExtractionRun)
        .where(*filters)
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return SyncRunListResponse(
        total=count_result.scalar_one(),
        items=[SyncRunResponse.model_validate(run) for run in result.scalars().all()],
    )


@router.get("/project/{project_id}/candidates", response_model=SyncCandidateListResponse, summary="列出待评审事实候选")
async def list_project_sync_candidates(
    project_id: str,
    request: Request,
    status: str | None = Query("pending", description="候选状态；默认只返回待评审候选"),
    entity_type: str | None = Query(None, description="事实类型：relationship/goldfinger"),
    run_id: str | None = Query(None, description="同步运行ID"),
    chapter_id: str | None = Query(None, description="来源章节ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SyncCandidateListResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(project_id, user_id, db)

    filters = [ExtractionCandidate.project_id == project_id]
    if status is not None:
        filters.append(ExtractionCandidate.status == status)
    if entity_type is not None:
        filters.append(ExtractionCandidate.candidate_type == entity_type.strip().lower())
    else:
        filters.append(ExtractionCandidate.candidate_type.in_(["relationship", "goldfinger", "world_fact"]))
    if run_id is not None:
        filters.append(ExtractionCandidate.run_id == run_id)
    if chapter_id is not None:
        filters.append(ExtractionCandidate.source_chapter_id == chapter_id)

    count_result = await db.execute(select(func.count(ExtractionCandidate.id)).where(*filters))
    result = await db.execute(
        select(ExtractionCandidate)
        .where(*filters)
        .order_by(ExtractionCandidate.created_at.desc(), ExtractionCandidate.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return SyncCandidateListResponse(
        total=count_result.scalar_one(),
        items=[SyncCandidateResponse.model_validate(candidate) for candidate in result.scalars().all()],
    )


@router.post("/runs/{run_id}/retry", response_model=SyncRunResponse, summary="重试同步运行")
async def retry_sync_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SyncRunResponse:
    user_id = _current_user_id(request)
    _ = await _get_run_for_user(run_id, user_id, db)
    try:
        await db.run_sync(lambda session: ChapterFactSyncService(session).retry_run(run_id))
    except ValueError as exc:
        await db.rollback()
        _structured_error(400, code="sync_retry_failed", message=str(exc))
    await db.commit()
    return SyncRunResponse.model_validate(await _get_run_for_user(run_id, user_id, db))


@router.post("/candidates/{candidate_id}/approve", response_model=SyncCandidateReviewResponse, summary="批准事实候选")
async def approve_sync_candidate(
    candidate_id: str,
    payload: SyncCandidateApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SyncCandidateReviewResponse:
    user_id = _current_user_id(request)
    candidate = await _get_candidate_for_user(candidate_id, user_id, db)
    if candidate.status != "pending":
        _structured_error(400, code="sync_candidate_not_pending", message=f"candidate is {candidate.status}")

    if candidate.candidate_type == "goldfinger":
        result = await db.run_sync(
            lambda session: GoldfingerSyncService(session).accept_candidate(
                candidate_id,
                reviewer_user_id=user_id,
                target_id=payload.target_id,
                override=payload.override,
            )
        )
        if not result.changed:
            await db.rollback()
            _structured_error(400, code="sync_goldfinger_approve_failed", message=result.reason or "金手指候选批准失败")
        await db.commit()
        return SyncCandidateReviewResponse(
            changed=True,
            reason=result.reason,
            candidate=await _candidate_response(candidate_id, db),
        )

    merge_supported = {"character", "organization", "profession", "relationship", "organization_affiliation", "profession_assignment"}
    if candidate.candidate_type not in merge_supported:
        _structured_error(501, code="sync_candidate_type_unsupported", message=f"候选类型暂不支持批准: {candidate.candidate_type}")

    result = await db.run_sync(
        lambda session: CandidateMergeService(session).accept_candidate(
            candidate_id,
            reviewer_user_id=user_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            override=payload.override,
            supersedes_candidate_id=payload.supersedes_candidate_id,
        )
    )
    if not result.changed:
        await db.rollback()
        _structured_error(400, code="sync_candidate_approve_failed", message=result.reason or "候选批准失败")
    await db.commit()
    return SyncCandidateReviewResponse(
        changed=True,
        reason=result.reason,
        candidate=await _candidate_response(candidate_id, db),
    )


@router.post("/candidates/{candidate_id}/reject", response_model=SyncCandidateReviewResponse, summary="拒绝事实候选")
async def reject_sync_candidate(
    candidate_id: str,
    payload: SyncCandidateRejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SyncCandidateReviewResponse:
    user_id = _current_user_id(request)
    candidate = await _get_candidate_for_user(candidate_id, user_id, db)
    if candidate.status != "pending":
        _structured_error(400, code="sync_candidate_not_pending", message=f"candidate is {candidate.status}")

    result = await db.run_sync(
        lambda session: CandidateMergeService(session).reject_candidate(
            candidate_id,
            reviewer_user_id=user_id,
            reason=payload.reason,
        )
    )
    if not result.changed:
        await db.rollback()
        _structured_error(400, code="sync_candidate_reject_failed", message=result.reason or "候选拒绝失败")
    await db.commit()
    return SyncCandidateReviewResponse(
        changed=True,
        reason=result.reason,
        candidate=await _candidate_response(candidate_id, db),
    )
