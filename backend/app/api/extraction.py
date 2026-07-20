"""Extraction run and candidate review API."""

from __future__ import annotations
from datetime import UTC, datetime

from typing import Callable, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.common import verify_project_access
from app.database import get_db
from app.models.project import Project
from app.models.relationship import ExtractionCandidate, ExtractionRun
from app.schemas.extraction import (
    CandidateAcceptRequest,
    CandidateBatchReviewFailure,
    CandidateBatchReviewRequest,
    CandidateBatchReviewResponse,
    CandidateMergeRequest,
    CandidateRejectRequest,
    CandidateReviewResponse,
    CandidateRollbackRequest,
    ExtractionCandidateListResponse,
    ExtractionCandidateResponse,
    ExtractionCandidateStatus,
    ExtractionCandidateType,
    ExtractionRunListResponse,
    ExtractionRunResponse,
    ExtractionRunStatus,
    ManualReextractChapterRequest,
    ManualReextractProjectRequest,
    ManualReextractRangeRequest,
    ManualReextractResponse,
)
from app.services.candidate_merge_service import CandidateMergeService, MergeResult
from app.services.goldfinger_sync_service import GoldfingerSyncResult, GoldfingerSyncService
from app.services.extraction_service import ExtractionTriggerService

router = APIRouter(prefix="/extraction", tags=["抽取评审"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _structured_error(status_code: int, *, code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _verify_project_filter(project_id: str | None, user_id: str, db: AsyncSession) -> None:
    if project_id is not None:
        _ = await verify_project_access(project_id, user_id, db)


async def _get_run_for_user(run_id: str, user_id: str, db: AsyncSession) -> ExtractionRun:
    result = await db.execute(select(ExtractionRun).where(ExtractionRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="抽取运行不存在")
    _ = await verify_project_access(run.project_id, user_id, db)
    return run


async def _get_candidate_for_user(candidate_id: str, user_id: str, db: AsyncSession) -> ExtractionCandidate:
    result = await db.execute(select(ExtractionCandidate).where(ExtractionCandidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="抽取候选不存在")
    _ = await verify_project_access(candidate.project_id, user_id, db)
    return candidate


async def _candidate_response(candidate_id: str, db: AsyncSession) -> ExtractionCandidateResponse:
    result = await db.execute(select(ExtractionCandidate).where(ExtractionCandidate.id == candidate_id))
    candidate = result.scalar_one()
    return ExtractionCandidateResponse.model_validate(candidate)


def _apply_canonical_target_filter(query, canonical_target: str | None):
    if not canonical_target:
        return query
    target = canonical_target.strip()
    if target.lower() in {"none", "null", "unassigned"}:
        return query.where(
            ExtractionCandidate.canonical_target_type.is_(None),
            ExtractionCandidate.canonical_target_id.is_(None),
        )
    if ":" in target:
        target_type, target_id = target.split(":", 1)
        return query.where(
            ExtractionCandidate.canonical_target_type == target_type.strip(),
            ExtractionCandidate.canonical_target_id == target_id.strip(),
        )
    return query.where(ExtractionCandidate.canonical_target_id == target)


ReviewResult = MergeResult | GoldfingerSyncResult


def _accept_candidate_sync(
    session: Session,
    candidate_id: str,
    *,
    reviewer_user_id: str,
    target_type: str | None = None,
    target_id: str | None = None,
    override: bool = False,
    supersedes_candidate_id: str | None = None,
) -> ReviewResult:
    candidate = session.get(ExtractionCandidate, candidate_id)
    if candidate is not None and candidate.candidate_type == "goldfinger":
        result = GoldfingerSyncService(session).accept_candidate(
            candidate_id,
            reviewer_user_id=reviewer_user_id,
            target_id=target_id,
            override=override,
        )
        if result.changed and supersedes_candidate_id:
            superseded = session.get(ExtractionCandidate, supersedes_candidate_id)
            if superseded is not None and superseded.id != candidate_id:
                superseded.status = "superseded"
                superseded.reviewed_at = superseded.reviewed_at or datetime.now(UTC).replace(tzinfo=None)
                candidate.supersedes_candidate_id = superseded.id
        session.flush()
        return result
    return CandidateMergeService(session).accept_candidate(
        candidate_id,
        reviewer_user_id=reviewer_user_id,
        target_type=target_type,
        target_id=target_id,
        override=override,
        supersedes_candidate_id=supersedes_candidate_id,
    )


def _preserve_review_reason(session: Session, candidate_id: str, reason: str | None) -> None:
    if not reason:
        return
    candidate = session.get(ExtractionCandidate, candidate_id)
    if candidate is not None and candidate.status == "pending":
        candidate.review_required_reason = reason
        session.flush()


def _run_batch_review_item(
    session: Session,
    candidate: ExtractionCandidate,
    *,
    action: Literal["accept", "reject"],
    reviewer_user_id: str,
    reason: str,
) -> ReviewResult:
    savepoint = session.begin_nested()
    try:
        if action == "accept":
            result = _accept_candidate_sync(
                session,
                candidate.id,
                reviewer_user_id=reviewer_user_id,
                target_type=candidate.canonical_target_type,
                target_id=candidate.canonical_target_id,
            )
        else:
            result = CandidateMergeService(session).reject_candidate(
                candidate.id,
                reviewer_user_id=reviewer_user_id,
                reason=reason,
            )
        if result.changed:
            savepoint.commit()
        else:
            savepoint.rollback()
            _preserve_review_reason(session, candidate.id, result.reason)
        return result
    except Exception:
        if savepoint.is_active:
            savepoint.rollback()
        raise


async def _review_candidate(
    *,
    candidate_id: str,
    user_id: str,
    db: AsyncSession,
    operation: Callable[[Session], ReviewResult],
    failure_code: str,
    failure_message: str,
) -> CandidateReviewResponse:
    _ = await _get_candidate_for_user(candidate_id, user_id, db)
    try:
        result = await db.run_sync(operation)
    except Exception as exc:
        await db.rollback()
        _structured_error(400, code=failure_code, message=str(exc) or failure_message)
    if not result.changed:
        await db.rollback()
        if result.reason:
            await db.run_sync(lambda session: _preserve_review_reason(session, candidate_id, result.reason))
            await db.commit()
        _structured_error(
            400,
            code=failure_code,
            message=result.reason or failure_message,
        )
    await db.commit()
    candidate = await _candidate_response(candidate_id, db)
    return CandidateReviewResponse(changed=True, reason=result.reason, candidate=candidate)


@router.get("/runs", response_model=ExtractionRunListResponse, summary="列出抽取运行")
async def list_extraction_runs(
    request: Request,
    project_id: str | None = Query(None, description="项目ID"),
    status: ExtractionRunStatus | None = Query(None, description="运行状态"),
    chapter_id: str | None = Query(None, description="章节ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ExtractionRunListResponse:
    user_id = _current_user_id(request)
    await _verify_project_filter(project_id, user_id, db)

    base_filters = [Project.user_id == user_id]
    if project_id is not None:
        base_filters.append(ExtractionRun.project_id == project_id)
    if status is not None:
        base_filters.append(ExtractionRun.status == status)
    if chapter_id is not None:
        base_filters.append(ExtractionRun.chapter_id == chapter_id)

    count_result = await db.execute(
        select(func.count(ExtractionRun.id)).join(Project, ExtractionRun.project_id == Project.id).where(*base_filters)
    )
    result = await db.execute(
        select(ExtractionRun)
        .join(Project, ExtractionRun.project_id == Project.id)
        .where(*base_filters)
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return ExtractionRunListResponse(
        total=count_result.scalar_one(),
        items=[ExtractionRunResponse.model_validate(run) for run in result.scalars().all()],
    )


@router.get("/runs/{run_id}", response_model=ExtractionRunResponse, summary="获取抽取运行详情")
async def get_extraction_run(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ExtractionRunResponse:
    user_id = _current_user_id(request)
    return ExtractionRunResponse.model_validate(await _get_run_for_user(run_id, user_id, db))


@router.get("/candidates", response_model=ExtractionCandidateListResponse, summary="列出抽取候选")
async def list_extraction_candidates(
    request: Request,
    project_id: str | None = Query(None, description="项目ID"),
    status: ExtractionCandidateStatus | None = Query(None, description="候选状态"),
    candidate_type: ExtractionCandidateType | None = Query(None, alias="type", description="候选类型"),
    chapter_id: str | None = Query(None, description="来源章节ID"),
    run_id: str | None = Query(None, description="抽取运行ID"),
    canonical_target: str | None = Query(None, description="目标过滤：none、target_id 或 type:target_id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ExtractionCandidateListResponse:
    user_id = _current_user_id(request)
    await _verify_project_filter(project_id, user_id, db)

    base_filters = [Project.user_id == user_id]
    if project_id is not None:
        base_filters.append(ExtractionCandidate.project_id == project_id)
    if status is not None:
        base_filters.append(ExtractionCandidate.status == status)
    if candidate_type is not None:
        base_filters.append(ExtractionCandidate.candidate_type == candidate_type)
    if chapter_id is not None:
        base_filters.append(ExtractionCandidate.source_chapter_id == chapter_id)
    if run_id is not None:
        base_filters.append(ExtractionCandidate.run_id == run_id)

    count_query = (
        select(func.count(ExtractionCandidate.id))
        .join(Project, ExtractionCandidate.project_id == Project.id)
        .where(*base_filters)
    )
    item_query = (
        select(ExtractionCandidate)
        .join(Project, ExtractionCandidate.project_id == Project.id)
        .where(*base_filters)
    )
    count_query = _apply_canonical_target_filter(count_query, canonical_target)
    item_query = _apply_canonical_target_filter(item_query, canonical_target)

    count_result = await db.execute(count_query)
    result = await db.execute(
        item_query.order_by(ExtractionCandidate.created_at.desc(), ExtractionCandidate.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return ExtractionCandidateListResponse(
        total=count_result.scalar_one(),
        items=[ExtractionCandidateResponse.model_validate(candidate) for candidate in result.scalars().all()],
    )


@router.post("/candidates/batch-accept", response_model=CandidateBatchReviewResponse, summary="批量接受抽取候选")
async def batch_accept_extraction_candidates(
    payload: CandidateBatchReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CandidateBatchReviewResponse:
    user_id = _current_user_id(request)
    candidates = [await _get_candidate_for_user(candidate_id, user_id, db) for candidate_id in payload.candidate_ids]
    priority = {
        "character": 0,
        "organization": 0,
        "profession": 0,
        "goldfinger": 0,
        "relationship": 1,
        "organization_affiliation": 2,
        "profession_assignment": 2,
    }
    candidates.sort(key=lambda candidate: priority.get(candidate.candidate_type, 3))
    changed_ids: list[str] = []
    failures: list[CandidateBatchReviewFailure] = []
    for candidate in candidates:
        try:
            result = await db.run_sync(
                lambda session, row=candidate: _run_batch_review_item(
                    session,
                    row,
                    action="accept",
                    reviewer_user_id=user_id,
                    reason="批量接受",
                )
            )
            if result.changed:
                changed_ids.append(candidate.id)
            else:
                failures.append(CandidateBatchReviewFailure(candidate_id=candidate.id, reason=result.reason or "候选未发生变化"))
        except Exception as exc:
            failures.append(CandidateBatchReviewFailure(candidate_id=candidate.id, reason=str(exc) or "候选接受失败"))
    await db.commit()
    reviewed = [await _candidate_response(candidate_id, db) for candidate_id in changed_ids]
    return CandidateBatchReviewResponse(changed=len(reviewed), failures=failures, candidates=reviewed)


@router.post("/candidates/batch-reject", response_model=CandidateBatchReviewResponse, summary="批量拒绝抽取候选")
async def batch_reject_extraction_candidates(
    payload: CandidateBatchReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CandidateBatchReviewResponse:
    user_id = _current_user_id(request)
    candidates = [await _get_candidate_for_user(candidate_id, user_id, db) for candidate_id in payload.candidate_ids]
    changed_ids: list[str] = []
    failures: list[CandidateBatchReviewFailure] = []
    reject_reason = payload.reason or "批量拒绝"
    for candidate in candidates:
        try:
            result = await db.run_sync(
                lambda session, row=candidate: _run_batch_review_item(
                    session,
                    row,
                    action="reject",
                    reviewer_user_id=user_id,
                    reason=reject_reason,
                )
            )
            if result.changed:
                changed_ids.append(candidate.id)
            else:
                failures.append(CandidateBatchReviewFailure(candidate_id=candidate.id, reason=result.reason or "候选未发生变化"))
        except Exception as exc:
            failures.append(CandidateBatchReviewFailure(candidate_id=candidate.id, reason=str(exc) or "候选拒绝失败"))
    await db.commit()
    reviewed = [await _candidate_response(candidate_id, db) for candidate_id in changed_ids]
    return CandidateBatchReviewResponse(changed=len(reviewed), failures=failures, candidates=reviewed)


@router.get("/candidates/{candidate_id}", response_model=ExtractionCandidateResponse, summary="获取抽取候选详情")
async def get_extraction_candidate(
    candidate_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ExtractionCandidateResponse:
    user_id = _current_user_id(request)
    return ExtractionCandidateResponse.model_validate(await _get_candidate_for_user(candidate_id, user_id, db))


@router.post("/reextract/project", response_model=ManualReextractResponse, summary="手动重新抽取整个项目")
async def manual_reextract_project(
    payload: ManualReextractProjectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ManualReextractResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(payload.project_id, user_id, db)
    runs = await db.run_sync(
        lambda session: [
            session.get(ExtractionRun, result.run_id)
            for result in ExtractionTriggerService(session).trigger_project(
                project_id=payload.project_id,
                user_id=user_id,
                trigger_source="manual_project",
                force=True,
                enabled=True,
                supersede_prior=False,
            )
        ]
    )
    await db.commit()
    concrete_runs = [run for run in runs if run is not None]
    return ManualReextractResponse(
        project_id=payload.project_id,
        scope="project",
        total_runs=len(concrete_runs),
        runs=[ExtractionRunResponse.model_validate(run) for run in concrete_runs],
    )


@router.post("/reextract/chapter", response_model=ManualReextractResponse, summary="手动重新抽取单章")
async def manual_reextract_chapter(
    payload: ManualReextractChapterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ManualReextractResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(payload.project_id, user_id, db)
    run = await db.run_sync(
        lambda session: (
            session.get(ExtractionRun, result.run_id)
            if (
                result := ExtractionTriggerService(session).trigger_chapter(
                    project_id=payload.project_id,
                    chapter_id=payload.chapter_id,
                    user_id=user_id,
                    trigger_source="manual_chapter",
                    force=True,
                    enabled=True,
                    supersede_prior=False,
                    source_metadata={"manual_scope": "chapter"},
                )
            )
            is not None
            else None
        )
    )
    await db.commit()
    if run is None:
        _structured_error(404, code="manual_reextract_failed", message="章节不存在或抽取未创建运行")
    return ManualReextractResponse(
        project_id=payload.project_id,
        scope="chapter",
        total_runs=1,
        runs=[ExtractionRunResponse.model_validate(run)],
    )


@router.post("/reextract/range", response_model=ManualReextractResponse, summary="手动重新抽取章节范围")
async def manual_reextract_range(
    payload: ManualReextractRangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ManualReextractResponse:
    user_id = _current_user_id(request)
    _ = await verify_project_access(payload.project_id, user_id, db)
    if payload.end_chapter_number < payload.start_chapter_number:
        _structured_error(400, code="invalid_chapter_range", message="结束章节不能小于起始章节")
    runs = await db.run_sync(
        lambda session: [
            session.get(ExtractionRun, result.run_id)
            for result in ExtractionTriggerService(session).trigger_chapter_range(
                project_id=payload.project_id,
                user_id=user_id,
                start_chapter_number=payload.start_chapter_number,
                end_chapter_number=payload.end_chapter_number,
                trigger_source="manual_range",
                force=True,
                enabled=True,
                supersede_prior=False,
            )
        ]
    )
    await db.commit()
    concrete_runs = [run for run in runs if run is not None]
    return ManualReextractResponse(
        project_id=payload.project_id,
        scope="range",
        total_runs=len(concrete_runs),
        runs=[ExtractionRunResponse.model_validate(run) for run in concrete_runs],
    )


@router.post("/candidates/{candidate_id}/accept", response_model=CandidateReviewResponse, summary="接受抽取候选")
async def accept_extraction_candidate(
    candidate_id: str,
    payload: CandidateAcceptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CandidateReviewResponse:
    user_id = _current_user_id(request)
    return await _review_candidate(
        candidate_id=candidate_id,
        user_id=user_id,
        db=db,
        operation=lambda session: _accept_candidate_sync(
            session,
            candidate_id,
            reviewer_user_id=user_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            override=payload.override,
            supersedes_candidate_id=payload.supersedes_candidate_id,
        ),
        failure_code="candidate_accept_failed",
        failure_message="候选接受失败",
    )


@router.post("/candidates/{candidate_id}/reject", response_model=CandidateReviewResponse, summary="拒绝抽取候选")
async def reject_extraction_candidate(
    candidate_id: str,
    payload: CandidateRejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CandidateReviewResponse:
    user_id = _current_user_id(request)
    return await _review_candidate(
        candidate_id=candidate_id,
        user_id=user_id,
        db=db,
        operation=lambda session: CandidateMergeService(session).reject_candidate(
            candidate_id,
            reviewer_user_id=user_id,
            reason=payload.reason,
        ),
        failure_code="candidate_reject_failed",
        failure_message="候选拒绝失败",
    )


@router.post("/candidates/{candidate_id}/merge", response_model=CandidateReviewResponse, summary="合并抽取候选")
async def merge_extraction_candidate(
    candidate_id: str,
    payload: CandidateMergeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CandidateReviewResponse:
    user_id = _current_user_id(request)
    return await _review_candidate(
        candidate_id=candidate_id,
        user_id=user_id,
        db=db,
        operation=lambda session: _accept_candidate_sync(
            session,
            candidate_id,
            reviewer_user_id=user_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            override=payload.override,
        ),
        failure_code="candidate_merge_failed",
        failure_message="候选合并失败",
    )


@router.post("/candidates/{candidate_id}/rollback", response_model=CandidateReviewResponse, summary="回滚候选合并")
async def rollback_extraction_candidate(
    candidate_id: str,
    payload: CandidateRollbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CandidateReviewResponse:
    user_id = _current_user_id(request)
    return await _review_candidate(
        candidate_id=candidate_id,
        user_id=user_id,
        db=db,
        operation=lambda session: CandidateMergeService(session).rollback_candidate(
            candidate_id,
            reviewer_user_id=user_id,
            reason=payload.reason,
        ),
        failure_code="candidate_rollback_failed",
        failure_message="候选回滚失败",
    )
