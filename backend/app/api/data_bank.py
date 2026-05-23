"""Data Bank / local RAG API."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import verify_project_access
from app.database import get_db
from app.services.data_bank_service import (
    DataBankService,
    DataBankValidationError,
    decode_local_text_upload,
    metadata_without_remote_url,
    reject_remote_reference,
    validate_upload_filename,
)


router = APIRouter(prefix="/projects/{project_id}/data-bank", tags=["Data Bank"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return str(user_id)


def _bad_request_from_validation(exc: DataBankValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _reject_top_level_remote_aliases(payload: "DataBankSnippetCreate") -> None:
    reject_remote_reference(payload.source_url)
    for key in ("url", "remote_url"):
        if payload.model_extra and key in payload.model_extra:
            reject_remote_reference(str(payload.model_extra.get(key)))


class DataBankSnippetCreate(BaseModel):
    """Create a Data Bank item from local pasted text. Client user_id is ignored."""

    title: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1)
    metadata: dict[str, Any] | None = None
    source_url: str | None = Field(None, description="远程URL兼容字段：如传入会被拒绝")
    user_id: str | None = Field(None, description="兼容字段：服务端会忽略客户端传入值")

    model_config = ConfigDict(extra="allow")

    @field_validator("title", "text")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class DataBankItemResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    title: str
    source_type: str
    filename: str | None = None
    content_type: str | None = None
    content_hash: str
    chunk_count: int
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DataBankItemListResponse(BaseModel):
    total: int
    items: list[DataBankItemResponse] = Field(default_factory=list)


class DataBankRetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class DataBankRetrievalResultResponse(BaseModel):
    order: int
    source_type: str
    item_source_type: str
    item_id: str
    chunk_id: str
    title: str
    filename: str | None = None
    chunk_index: int
    score: float
    matched_terms: list[str]
    content: str
    char_start: int
    char_end: int
    content_hash: str


class DataBankRetrievalTraceResponse(BaseModel):
    project_id: str
    query: str
    strategy: str
    total_candidates: int
    returned_count: int
    results: list[DataBankRetrievalResultResponse] = Field(default_factory=list)


@router.post("/snippets", response_model=DataBankItemResponse, summary="创建Data Bank本地文本片段")
async def create_data_bank_snippet(
    project_id: str,
    payload: DataBankSnippetCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        _reject_top_level_remote_aliases(payload)
        metadata = metadata_without_remote_url(payload.metadata)
        item = await DataBankService.create_text_item(
            db=db,
            project_id=project_id,
            user_id=user_id,
            title=payload.title,
            text=payload.text,
            source_type="snippet",
            metadata=metadata,
        )
    except DataBankValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return DataBankService.item_dict(item)


@router.post("/uploads", response_model=DataBankItemResponse, summary="上传Data Bank本地.txt/.md文件")
async def upload_data_bank_file(
    project_id: str,
    request: Request,
    title: str | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        filename = validate_upload_filename(file.filename)
        raw_bytes = await file.read()
        text = decode_local_text_upload(raw_bytes)
        item = await DataBankService.create_text_item(
            db=db,
            project_id=project_id,
            user_id=user_id,
            title=(title or filename).strip() or filename,
            text=text,
            source_type="upload",
            filename=filename,
            content_type=file.content_type,
            metadata={"upload_filename": filename},
        )
    except DataBankValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return DataBankService.item_dict(item)


@router.get("", response_model=DataBankItemListResponse, summary="列出Data Bank条目")
async def list_data_bank_items(
    project_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    total, items = await DataBankService.list_items(
        db=db,
        project_id=project_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": [DataBankService.item_dict(item) for item in items]}


@router.post("/retrieve", response_model=DataBankRetrievalTraceResponse, summary="确定性检索Data Bank切片")
async def retrieve_data_bank(
    project_id: str,
    payload: DataBankRetrievalRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    try:
        trace = await DataBankService.retrieve(
            db=db,
            project_id=project_id,
            user_id=user_id,
            query=payload.query,
            limit=payload.limit,
        )
    except DataBankValidationError as exc:
        raise _bad_request_from_validation(exc) from exc
    return DataBankService.retrieval_trace_dict(trace)


@router.delete("/{item_id}", summary="删除Data Bank条目")
async def delete_data_bank_item(
    project_id: str,
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    user_id = _current_user_id(request)
    await verify_project_access(project_id, user_id, db)
    deleted = await DataBankService.delete_item(db=db, item_id=item_id, project_id=project_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Data Bank条目不存在")
    return {"deleted": True}
