"""Safe local project asset storage service."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import uuid
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PROJECT_ROOT
from app.models.project_asset import ProjectAsset


LOCAL_ASSET_STORAGE_ROOT = PROJECT_ROOT / "storage" / "project_assets"
MAX_ASSET_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_ASSET_TYPES = {"avatar", "background", "sprite"}
ALLOWED_EXTENSION_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class ProjectAssetValidationError(ValueError):
    """Raised when a local asset upload is not allowed."""


def validate_asset_type(asset_type: str | None) -> str:
    normalized = str(asset_type or "").strip().lower()
    if normalized not in ALLOWED_ASSET_TYPES:
        raise ProjectAssetValidationError("资源类型仅支持 avatar、background 或 sprite")
    return normalized


def validate_original_filename(filename: str | None) -> str:
    name = str(filename or "").strip()
    if not name:
        raise ProjectAssetValidationError("上传文件名不能为空")
    if "\x00" in name or "/" in name or "\\" in name:
        raise ProjectAssetValidationError("上传文件名不能包含路径分隔符")
    if name in {".", ".."} or ".." in Path(name).parts:
        raise ProjectAssetValidationError("上传文件名不能包含路径穿越片段")
    if Path(name).name != name:
        raise ProjectAssetValidationError("上传文件名必须是普通文件名")
    return name


def validate_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSION_MIME:
        allowed = "、".join(sorted(ALLOWED_EXTENSION_MIME))
        raise ProjectAssetValidationError(f"本地资源仅支持图片扩展名：{allowed}")
    return extension


def normalize_content_type(content_type: str | None) -> str:
    normalized = str(content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if not normalized:
        raise ProjectAssetValidationError("上传文件缺少MIME类型")
    if normalized not in set(ALLOWED_EXTENSION_MIME.values()):
        raise ProjectAssetValidationError("上传文件MIME类型不受支持")
    return normalized


def sniff_image_mime(raw_bytes: bytes) -> str | None:
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def _safe_storage_segment(value: str) -> str:
    raw = str(value or "").strip()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    segment = _SAFE_SEGMENT_RE.sub("_", raw)[:80].strip("._-") or "item"
    return f"{segment}-{digest}"


def _resolve_storage_path(storage_key: str) -> Path:
    root = LOCAL_ASSET_STORAGE_ROOT.resolve()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ProjectAssetValidationError("资源存储路径越界") from exc
    return path


def _make_storage_key(*, user_id: str, project_id: str, storage_filename: str) -> str:
    storage_key = "/".join([
        _safe_storage_segment(user_id),
        _safe_storage_segment(project_id),
        storage_filename,
    ])
    _resolve_storage_path(storage_key)
    return storage_key


def _validate_file_payload(*, filename: str, content_type: str | None, raw_bytes: bytes) -> tuple[str, str, str]:
    extension = validate_extension(filename)
    declared_mime = normalize_content_type(content_type)
    expected_mime = ALLOWED_EXTENSION_MIME[extension]
    if declared_mime != expected_mime:
        raise ProjectAssetValidationError("上传文件扩展名与MIME类型不匹配")
    size = len(raw_bytes)
    if size <= 0:
        raise ProjectAssetValidationError("上传文件不能为空")
    if size > MAX_ASSET_UPLOAD_BYTES:
        limit_mb = MAX_ASSET_UPLOAD_BYTES // (1024 * 1024)
        raise ProjectAssetValidationError(f"上传文件大小不能超过 {limit_mb}MB")
    detected_mime = sniff_image_mime(raw_bytes)
    if detected_mime != expected_mime:
        raise ProjectAssetValidationError("上传文件内容与图片类型不匹配")
    return extension, expected_mime, hashlib.sha256(raw_bytes).hexdigest()


class ProjectAssetService:
    """Async DB and filesystem helpers for local-only project assets."""

    @staticmethod
    def asset_dict(asset: ProjectAsset) -> dict[str, object]:
        file_url = f"/api/projects/{quote(asset.project_id)}/assets/{quote(asset.id)}/file"
        return {
            "id": asset.id,
            "project_id": asset.project_id,
            "user_id": asset.user_id,
            "asset_type": asset.asset_type,
            "display_name": asset.display_name,
            "original_filename": asset.original_filename,
            "storage_filename": asset.storage_filename,
            "mime_type": asset.mime_type,
            "file_size": asset.file_size,
            "content_hash": asset.content_hash,
            "file_url": file_url,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }

    @staticmethod
    def resolve_asset_path(asset: ProjectAsset) -> Path:
        return _resolve_storage_path(asset.storage_key)

    @classmethod
    async def create_asset(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        asset_type: str,
        display_name: str | None,
        original_filename: str | None,
        content_type: str | None,
        raw_bytes: bytes,
    ) -> ProjectAsset:
        normalized_type = validate_asset_type(asset_type)
        safe_original_filename = validate_original_filename(original_filename)
        extension, mime_type, content_hash = _validate_file_payload(
            filename=safe_original_filename,
            content_type=content_type,
            raw_bytes=raw_bytes,
        )
        asset_id = str(uuid.uuid4())
        storage_filename = f"{asset_id}{extension}"
        storage_key = _make_storage_key(user_id=user_id, project_id=project_id, storage_filename=storage_filename)
        file_path = _resolve_storage_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(raw_bytes)

        asset = ProjectAsset(
            id=asset_id,
            project_id=project_id,
            user_id=user_id,
            asset_type=normalized_type,
            display_name=(display_name or Path(safe_original_filename).stem).strip()[:200] or Path(safe_original_filename).stem,
            original_filename=safe_original_filename,
            storage_key=storage_key,
            storage_filename=storage_filename,
            mime_type=mime_type,
            file_size=len(raw_bytes),
            content_hash=content_hash,
        )
        db.add(asset)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            if file_path.exists():
                file_path.unlink()
            raise
        await db.refresh(asset)
        return asset

    @classmethod
    async def list_assets(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        asset_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[ProjectAsset]]:
        filters = [ProjectAsset.project_id == project_id, ProjectAsset.user_id == user_id]
        if asset_type:
            filters.append(ProjectAsset.asset_type == validate_asset_type(asset_type))
        count_result = await db.execute(select(func.count(ProjectAsset.id)).where(*filters))
        result = await db.execute(
            select(ProjectAsset)
            .where(*filters)
            .order_by(ProjectAsset.created_at.desc(), ProjectAsset.id.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return int(count_result.scalar_one() or 0), list(result.scalars().all())

    @classmethod
    async def get_asset(
        cls,
        *,
        db: AsyncSession,
        asset_id: str,
        project_id: str,
        user_id: str,
    ) -> ProjectAsset | None:
        result = await db.execute(
            select(ProjectAsset).where(
                ProjectAsset.id == asset_id,
                ProjectAsset.project_id == project_id,
                ProjectAsset.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def delete_asset(cls, *, db: AsyncSession, asset_id: str, project_id: str, user_id: str) -> bool:
        asset = await cls.get_asset(db=db, asset_id=asset_id, project_id=project_id, user_id=user_id)
        if asset is None:
            return False
        file_path = cls.resolve_asset_path(asset)
        if file_path.exists():
            file_path.unlink()
        await db.delete(asset)
        await db.commit()
        return True


project_asset_service = ProjectAssetService()
