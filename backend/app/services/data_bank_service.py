"""Data Bank ingestion and deterministic RAG retrieval service."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_bank import DataBankChunk, DataBankItem


SUPPORTED_UPLOAD_EXTENSIONS = {".txt", ".md"}
DEFAULT_CHUNK_CHARS = 900
DEFAULT_CHUNK_OVERLAP = 120
DATA_BANK_MAX_TEXT_BYTES = 1_000_000


class DataBankValidationError(ValueError):
    """Raised when local Data Bank ingestion input is not allowed."""


@dataclass(frozen=True, slots=True)
class DataBankChunkDraft:
    index: int
    content: str
    char_start: int
    char_end: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class DataBankRetrievalResult:
    order: int
    item_id: str
    chunk_id: str
    title: str
    source_type: str
    filename: str | None
    chunk_index: int
    score: float
    matched_terms: tuple[str, ...]
    content: str
    char_start: int
    char_end: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class DataBankRetrievalTrace:
    project_id: str
    query: str
    total_candidates: int
    returned_count: int
    results: tuple[DataBankRetrievalResult, ...]
    strategy: str = "deterministic-lexical-v1"


def is_remote_reference(value: str | None) -> bool:
    """Return True for URL-like remote references. Local ingestion only is allowed."""

    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme.lower() in {"http", "https"}:
        return True
    return text.startswith("//")


def reject_remote_reference(value: str | None) -> None:
    if is_remote_reference(value):
        raise DataBankValidationError("Data Bank仅支持本地文本片段和本地.txt/.md上传，不支持远程URL导入")


def validate_upload_filename(filename: str | None) -> str:
    name = str(filename or "").strip()
    reject_remote_reference(name)
    if not name:
        raise DataBankValidationError("上传文件名不能为空")
    lowered = name.casefold()
    if not any(lowered.endswith(extension) for extension in SUPPORTED_UPLOAD_EXTENSIONS):
        raise DataBankValidationError("Data Bank仅支持上传.txt或.md文件")
    return name


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text_content(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise DataBankValidationError("Data Bank文本内容不能为空")
    enforce_text_size(normalized)
    return normalized


def enforce_text_size(text: str, *, max_bytes: int = DATA_BANK_MAX_TEXT_BYTES) -> None:
    """Reject oversized text before chunk generation or persistence."""
    if len(str(text or "").encode("utf-8")) > max_bytes:
        max_mb = max_bytes / 1_000_000
        raise DataBankValidationError(f"Data Bank文本内容超过大小限制（最大{max_mb:g}MB）")


def enforce_upload_size(raw_bytes: bytes, *, max_bytes: int = DATA_BANK_MAX_TEXT_BYTES) -> None:
    """Reject oversized local text uploads before decoding/ingestion."""
    if len(raw_bytes) > max_bytes:
        max_mb = max_bytes / 1_000_000
        raise DataBankValidationError(f"Data Bank上传文件超过大小限制（最大{max_mb:g}MB）")


def build_chunks(
    text: str,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> tuple[DataBankChunkDraft, ...]:
    """Build stable character-window chunks without embeddings or network calls."""

    content = normalize_text_content(text)
    safe_chunk_chars = max(100, chunk_chars)
    safe_overlap = max(0, min(chunk_overlap, safe_chunk_chars - 1))
    chunks: list[DataBankChunkDraft] = []
    start = 0
    index = 0
    while start < len(content):
        end = min(len(content), start + safe_chunk_chars)
        chunk_text = content[start:end].strip()
        leading_trim = len(content[start:end]) - len(content[start:end].lstrip())
        trailing_trim = len(content[start:end]) - len(content[start:end].rstrip())
        adjusted_start = start + leading_trim
        adjusted_end = end - trailing_trim
        if chunk_text:
            chunks.append(
                DataBankChunkDraft(
                    index=index,
                    content=chunk_text,
                    char_start=adjusted_start,
                    char_end=adjusted_end,
                    content_hash=_hash_text(chunk_text),
                )
            )
            index += 1
        if end >= len(content):
            break
        start = end - safe_overlap
    return tuple(chunks)


_TOKEN_RE = re.compile(r"[\w]+|[\u4e00-\u9fff]", re.UNICODE)


def _query_terms(query: str) -> tuple[str, ...]:
    seen: set[str] = set()
    terms: list[str] = []
    for token in _TOKEN_RE.findall(query.casefold()):
        if token and token not in seen:
            terms.append(token)
            seen.add(token)
    return tuple(terms)


def _phrase_parts(query: str) -> tuple[str, ...]:
    parts = [part.strip().casefold() for part in re.split(r"\s+", query) if part.strip()]
    return tuple(part for part in parts if len(part) > 1)


def _score_chunk(query: str, terms: Sequence[str], content: str) -> tuple[float, tuple[str, ...]]:
    folded_content = content.casefold()
    folded_query = query.strip().casefold()
    matched = tuple(term for term in terms if term in folded_content)
    score = float(len(matched))
    if folded_query and folded_query in folded_content:
        score += 5.0
    for part in _phrase_parts(query):
        if part in folded_content and part != folded_query:
            score += 2.0
    return score, matched


class DataBankService:
    """Async DB helpers for local-only Data Bank ingestion and retrieval.

    Storage strategy: source text and deterministic chunks are stored in the
    relational database. Retrieval deliberately uses a pure lexical scorer so
    tests and prompt traces are stable and no frontend or remote embeddings are
    needed. Existing Chroma-backed memory service remains untouched.
    """

    @staticmethod
    def item_dict(item: DataBankItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "user_id": item.user_id,
            "title": item.title,
            "source_type": item.source_type,
            "filename": item.filename,
            "content_type": item.content_type,
            "content_hash": item.content_hash,
            "chunk_count": item.chunk_count,
            "metadata": item.item_metadata,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def retrieval_trace_dict(trace: DataBankRetrievalTrace) -> dict[str, Any]:
        return {
            "project_id": trace.project_id,
            "query": trace.query,
            "strategy": trace.strategy,
            "total_candidates": trace.total_candidates,
            "returned_count": trace.returned_count,
            "results": [
                {
                    "order": result.order,
                    "source_type": "data_bank",
                    "item_source_type": result.source_type,
                    "item_id": result.item_id,
                    "chunk_id": result.chunk_id,
                    "title": result.title,
                    "filename": result.filename,
                    "chunk_index": result.chunk_index,
                    "score": result.score,
                    "matched_terms": list(result.matched_terms),
                    "content": result.content,
                    "char_start": result.char_start,
                    "char_end": result.char_end,
                    "content_hash": result.content_hash,
                }
                for result in trace.results
            ],
        }

    @classmethod
    async def create_text_item(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        title: str,
        text: str,
        source_type: str = "snippet",
        filename: str | None = None,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DataBankItem:
        if source_type not in {"snippet", "upload"}:
            raise DataBankValidationError("Data Bank来源类型无效")
        if metadata and is_remote_reference(str(metadata.get("source_url", ""))):
            reject_remote_reference(str(metadata.get("source_url")))
        if filename:
            reject_remote_reference(filename)
        content = normalize_text_content(text)
        chunks = build_chunks(content)
        item = DataBankItem(
            project_id=project_id,
            user_id=user_id,
            title=title.strip() or "未命名资料",
            source_type=source_type,
            filename=filename,
            content_type=content_type,
            content_hash=_hash_text(content),
            text_content=content,
            chunk_count=len(chunks),
            item_metadata=metadata,
        )
        db.add(item)
        await db.flush()
        for draft in chunks:
            db.add(
                DataBankChunk(
                    item_id=item.id,
                    project_id=project_id,
                    user_id=user_id,
                    chunk_index=draft.index,
                    content=draft.content,
                    char_start=draft.char_start,
                    char_end=draft.char_end,
                    content_hash=draft.content_hash,
                    chunk_metadata={"chunk_chars": DEFAULT_CHUNK_CHARS, "chunk_overlap": DEFAULT_CHUNK_OVERLAP},
                )
            )
        await db.commit()
        await db.refresh(item)
        return item

    @classmethod
    async def list_items(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[DataBankItem]]:
        filters = [DataBankItem.project_id == project_id, DataBankItem.user_id == user_id]
        count_result = await db.execute(select(func.count(DataBankItem.id)).where(*filters))
        result = await db.execute(
            select(DataBankItem)
            .where(*filters)
            .order_by(DataBankItem.created_at.desc(), DataBankItem.id.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return int(count_result.scalar_one() or 0), list(result.scalars().all())

    @classmethod
    async def retrieve(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        query: str,
        limit: int = 5,
    ) -> DataBankRetrievalTrace:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise DataBankValidationError("检索查询不能为空")
        terms = _query_terms(normalized_query)
        result = await db.execute(
            select(DataBankChunk, DataBankItem)
            .join(DataBankItem, DataBankChunk.item_id == DataBankItem.id)
            .where(
                DataBankChunk.project_id == project_id,
                DataBankChunk.user_id == user_id,
                DataBankItem.project_id == project_id,
                DataBankItem.user_id == user_id,
            )
        )
        rows = list(result.all())
        scored: list[tuple[float, tuple[str, ...], DataBankChunk, DataBankItem]] = []
        for chunk, item in rows:
            score, matched_terms = _score_chunk(normalized_query, terms, chunk.content)
            if score > 0:
                scored.append((score, matched_terms, chunk, item))
        scored.sort(
            key=lambda row: (
                -row[0],
                row[2].chunk_index,
                row[3].title.casefold(),
                row[3].id,
                row[2].id,
            )
        )
        selected = scored[: max(1, min(limit, 20))]
        trace_results = tuple(
            DataBankRetrievalResult(
                order=order,
                item_id=item.id,
                chunk_id=chunk.id,
                title=item.title,
                source_type=item.source_type,
                filename=item.filename,
                chunk_index=chunk.chunk_index,
                score=score,
                matched_terms=matched_terms,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                content_hash=chunk.content_hash,
            )
            for order, (score, matched_terms, chunk, item) in enumerate(selected, start=1)
        )
        return DataBankRetrievalTrace(
            project_id=project_id,
            query=normalized_query,
            total_candidates=len(rows),
            returned_count=len(trace_results),
            results=trace_results,
        )

    @classmethod
    async def delete_item(cls, *, db: AsyncSession, item_id: str, project_id: str, user_id: str) -> bool:
        result = await db.execute(
            select(DataBankItem).where(
                DataBankItem.id == item_id,
                DataBankItem.project_id == project_id,
                DataBankItem.user_id == user_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return False
        await db.delete(item)
        await db.commit()
        return True


def decode_local_text_upload(raw_bytes: bytes) -> str:
    enforce_upload_size(raw_bytes)
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataBankValidationError("上传文件必须是UTF-8编码的.txt或.md文本") from exc


def metadata_without_remote_url(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return metadata
    for key in ("source_url", "url", "remote_url"):
        if is_remote_reference(str(metadata.get(key, ""))):
            reject_remote_reference(str(metadata.get(key)))
    return metadata
