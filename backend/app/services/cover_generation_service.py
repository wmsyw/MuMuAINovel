"""小说封面生成服务"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PROJECT_ROOT
from app.logger import get_logger
from app.models.project import Project
from app.models.settings import Settings
from app.services.cover_providers.base_cover_provider import BaseCoverProvider, CoverGenerationResult
from app.services.cover_providers.gemini_cover_provider import GeminiCoverProvider
from app.services.cover_providers.grok_cover_provider import GrokCoverProvider
from app.services.cover_providers.openai_image_cover_provider import OpenAIImageCoverProvider
from app.services.prompt_service import PromptService

logger = get_logger(__name__)

COVER_WIDTH = 1024
COVER_HEIGHT = 1536
GENERATED_COVER_STORAGE_DIR = PROJECT_ROOT / "storage" / "generated_covers"
GENERATED_COVER_PUBLIC_PREFIX = "/generated-assets/covers"
GENERIC_COVER_FAILURE_MESSAGE = "封面生成失败，请稍后重试"


@dataclass
class CoverTestResult:
    success: bool
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None


class CoverGenerationService:
    """封面生成服务"""

    async def generate_cover(
        self,
        *,
        db: AsyncSession,
        user_id: str,
        project_id: str,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        project = await self._get_project(db=db, user_id=user_id, project_id=project_id)
        settings = await self._get_settings(db=db, user_id=user_id)
        self._validate_cover_settings(settings)

        if project.cover_status == "generating":
            raise HTTPException(status_code=409, detail="封面正在生成中，请勿重复提交")
        if project.cover_status == "ready" and project.cover_image_url and not overwrite:
            raise HTTPException(status_code=400, detail="当前项目已存在封面，如需覆盖请传入 overwrite=true")

        prompt = await PromptService.build_novel_cover_prompt(
            project,
            user_id=user_id,
            db=db,
        )
        project.cover_status = "generating"
        project.cover_error = None
        project.cover_prompt = prompt
        await db.commit()
        await db.refresh(project)

        try:
            provider = self._build_provider(settings)
            result = await provider.generate_cover(
                prompt=prompt,
                model=settings.cover_image_model or "",
                width=COVER_WIDTH,
                height=COVER_HEIGHT,
            )
            image_url = self._save_cover_file(
                user_id=user_id,
                project_id=project.id,
                content=result["content"],
                file_extension=result["file_extension"],
            )

            project.cover_image_url = image_url
            project.cover_status = "ready"
            project.cover_error = None
            project.cover_updated_at = datetime.utcnow()
            project.cover_prompt = result.get("revised_prompt") or prompt
            await db.commit()
            await db.refresh(project)

            return {
                "project_id": project.id,
                "cover_status": project.cover_status,
                "cover_image_url": project.cover_image_url,
                "cover_prompt": project.cover_prompt,
                "provider": result["provider"],
                "model": result["model"],
                "message": "封面生成成功",
            }
        except httpx.HTTPStatusError as exc:
            logger.error(
                "封面生成上游 HTTP 错误: project_id=%s fields=%s",
                project.id,
                self._http_status_error_log_fields(exc),
            )
            detail = self._extract_upstream_error_detail(exc)
            project.cover_status = "failed"
            project.cover_error = detail
            await db.commit()
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
        except HTTPException as exc:
            logger.error("封面生成业务错误: project_id=%s error=%s", project.id, exc.detail, exc_info=True)
            project.cover_status = "failed"
            project.cover_error = str(exc.detail)
            await db.commit()
            raise
        except Exception as exc:
            logger.error("封面生成失败: project_id=%s exception_type=%s", project.id, type(exc).__name__)
            project.cover_status = "failed"
            project.cover_error = GENERIC_COVER_FAILURE_MESSAGE
            await db.commit()
            raise HTTPException(status_code=500, detail=GENERIC_COVER_FAILURE_MESSAGE) from None

    async def test_cover_settings(
        self,
        *,
        provider: str,
        api_key: str,
        api_base_url: Optional[str],
        model: str,
    ) -> CoverTestResult:
        if not provider or not api_key or not model:
            raise HTTPException(status_code=400, detail="封面图片配置不完整，请填写 provider、api_key 和 model")

        normalized_provider, _ = self._normalize_provider_values(
            provider=provider,
            api_base_url=api_base_url,
            model=model,
        )

        provider_instance = self._build_provider_from_values(
            provider=provider,
            api_key=api_key,
            api_base_url=api_base_url,
            model=model,
        )
        test_prompt = (
            "Create a clean fantasy novel cover illustration, vertical book cover, "
            "standard 2:3 ratio, atmospheric lighting, no text, no watermark."
        )
        try:
            await provider_instance.generate_cover(
                prompt=test_prompt,
                model=model,
                width=COVER_WIDTH,
                height=COVER_HEIGHT,
            )
        except httpx.HTTPStatusError as exc:
            detail = self._extract_upstream_error_detail(exc)
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc

        return CoverTestResult(
            success=True,
            message="封面图片接口测试成功",
            provider=normalized_provider,
            model=model,
        )

    async def get_cover_download_path(
        self,
        *,
        db: AsyncSession,
        user_id: str,
        project_id: str,
    ) -> tuple[Project, Path]:
        project = await self._get_project(db=db, user_id=user_id, project_id=project_id)
        if project.cover_status != "ready" or not project.cover_image_url:
            raise HTTPException(status_code=404, detail="当前项目尚未生成可下载的封面")

        absolute_path = self._resolve_cover_path(project.cover_image_url)
        if not absolute_path.exists():
            raise HTTPException(status_code=404, detail="封面文件不存在，请重新生成")
        return project, absolute_path

    async def clear_cover_metadata(self, *, db: AsyncSession, project: Project) -> None:
        project.cover_image_url = None
        project.cover_prompt = None
        project.cover_status = "none"
        project.cover_error = None
        project.cover_updated_at = None
        await db.commit()

    async def _get_project(self, *, db: AsyncSession, user_id: str, project_id: str) -> Project:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == user_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        return project

    async def _get_settings(self, *, db: AsyncSession, user_id: str) -> Settings:
        result = await db.execute(select(Settings).where(Settings.user_id == user_id))
        settings = result.scalar_one_or_none()
        if not settings:
            raise HTTPException(status_code=400, detail="请先在设置页完成封面图片配置")
        return settings

    def _validate_cover_settings(self, settings: Settings) -> None:
        if not settings.cover_enabled:
            raise HTTPException(status_code=400, detail="封面图片功能未启用，请先在设置页开启")
        if not settings.cover_api_provider or not settings.cover_api_key or not settings.cover_image_model:
            raise HTTPException(status_code=400, detail="封面图片配置不完整，请前往设置页补全")

    def _build_provider(self, settings: Settings) -> BaseCoverProvider:
        return self._build_provider_from_values(
            provider=settings.cover_api_provider or "",
            api_key=settings.cover_api_key or "",
            api_base_url=settings.cover_api_base_url,
            model=settings.cover_image_model or "",
        )

    @staticmethod
    def _normalize_provider_values(
        *,
        provider: str,
        api_base_url: Optional[str],
        model: str,
    ) -> tuple[str, str]:
        """Normalize persisted provider values before selecting an implementation.

        Older settings used a single provider value for several OpenAI-compatible
        image gateways.  Keep those values runnable when their URL/model gives us
        an unambiguous route, but never recreate the old branded fallback URL.
        """
        provider_value = (provider or "").lower().strip()
        normalized_base_url = (api_base_url or "").rstrip("/")

        if provider_value == "mumu":
            model_value = (model or "").lower().strip()
            base_url_value = normalized_base_url.lower()
            if base_url_value.endswith("/v1beta"):
                provider_value = "gemini"
            elif model_value.startswith("gpt-image-"):
                provider_value = "openai"
            elif model_value.startswith("grok-") or "api.x.ai" in base_url_value:
                provider_value = "grok"
            elif normalized_base_url:
                # Preserve arbitrary OpenAI-compatible gateways and their model.
                provider_value = "openai"
            else:
                raise HTTPException(
                    status_code=400,
                    detail="封面图片 Provider 配置已过期，请在设置页重新选择 OpenAI、Gemini 或 Grok",
                )
        elif provider_value in {"custom", "openai-compatible", "openai_compatible"}:
            provider_value = "openai"

        return provider_value, normalized_base_url

    def _build_provider_from_values(
        self,
        *,
        provider: str,
        api_key: str,
        api_base_url: Optional[str],
        model: str,
    ) -> BaseCoverProvider:
        provider_value, normalized_base_url = self._normalize_provider_values(
            provider=provider,
            api_base_url=api_base_url,
            model=model,
        )
        if provider_value == "gemini":
            return GeminiCoverProvider(api_key=api_key, base_url=normalized_base_url)
        if provider_value == "grok":
            return GrokCoverProvider(api_key=api_key, base_url=normalized_base_url)
        if provider_value == "openai":
            return OpenAIImageCoverProvider(api_key=api_key, base_url=normalized_base_url)
        raise HTTPException(status_code=400, detail="当前版本仅支持 OpenAI、Gemini 或 Grok 封面图片 Provider")

    def _save_cover_file(
        self,
        *,
        user_id: str,
        project_id: str,
        content: bytes,
        file_extension: str,
    ) -> str:
        user_dir = GENERATED_COVER_STORAGE_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        safe_extension = (file_extension or "png").lstrip(".")
        filename = f"{project_id}_{timestamp}.{safe_extension}"
        file_path = user_dir / filename
        file_path.write_bytes(content)
        logger.info("封面文件已保存: project_id=%s path=%s", project_id, file_path)
        return f"{GENERATED_COVER_PUBLIC_PREFIX}/{quote(user_id)}/{quote(filename)}"

    def _resolve_cover_path(self, cover_image_url: Optional[str]) -> Path:
        if not cover_image_url:
            raise HTTPException(status_code=404, detail="当前项目尚未生成可下载的封面")

        if cover_image_url.startswith(f"{GENERATED_COVER_PUBLIC_PREFIX}/"):
            relative_path = cover_image_url.replace(f"{GENERATED_COVER_PUBLIC_PREFIX}/", "", 1)
            return GENERATED_COVER_STORAGE_DIR / relative_path

        if cover_image_url.startswith("/assets/generated_covers/"):
            relative_path = cover_image_url.replace("/assets/generated_covers/", "", 1)
            return GENERATED_COVER_STORAGE_DIR / relative_path

        raise HTTPException(status_code=404, detail="封面文件路径无效，请重新生成")

    @staticmethod
    def _extract_upstream_error_detail(exc: httpx.HTTPStatusError) -> str:
        response = exc.response
        if response is None:
            return "上游图片服务请求失败"
        return CoverGenerationService._generic_upstream_error_detail(response)

    @staticmethod
    def _generic_upstream_error_detail(response: httpx.Response) -> str:
        return f"上游图片服务请求失败 (HTTP {response.status_code})"

    @staticmethod
    def _http_status_error_log_fields(exc: httpx.HTTPStatusError) -> dict[str, int | str | dict[str, str]]:
        response = exc.response
        request = exc.request
        fields: dict[str, int | str | dict[str, str]] = {
            "status": response.status_code,
            "request_url": CoverGenerationService._sanitize_url_for_log(str(request.url)),
        }
        content_type = response.headers.get("content-type")
        if content_type:
            fields["content_type"] = content_type
        request_ids = {
            header: value
            for header in ("x-request-id", "request-id", "openai-request-id")
            if (value := response.headers.get(header))
        }
        if request_ids:
            fields["request_ids"] = request_ids
        return fields

    @staticmethod
    def _sanitize_url_for_log(value: str) -> str:
        try:
            parts = urlsplit(value)
            port = parts.port
        except ValueError:
            return "<invalid-url>"
        if not parts.hostname:
            return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))

        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        netloc = f"{host}:{port}" if port is not None else host
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


cover_generation_service = CoverGenerationService()
