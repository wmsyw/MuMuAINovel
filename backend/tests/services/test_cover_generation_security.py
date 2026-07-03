from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.cover_generation_service import CoverGenerationService
from app.models.project import Project
from app.models.settings import Settings
from app.services.cover_providers.base_cover_provider import BaseCoverProvider, CoverGenerationResult
from app.services.prompt_service import PromptService

pytestmark = pytest.mark.anyio

SIGNED_FALLBACK_URL = (
    "https://cdn.example.test/cover.png"
    "?X-Amz-Signature=download-secret&token=download-token"
    "#private-fragment"
)
RAW_UPSTREAM_BODY = "raw-sensitive-download-error body-secret"
SIGNED_JSON_ERROR_URL = "https://cdn.example.test/cover.webp?token=download-secret#private-fragment"
RAW_JSON_ERROR_DETAIL = f"raw-sensitive-provider-detail {SIGNED_JSON_ERROR_URL}"
RAW_PROVIDER_EXCEPTION = "raw-sensitive-provider-detail token=download-secret"
GENERIC_COVER_FAILURE = "封面生成失败，请稍后重试"


class _SignedUrlFailingProvider(BaseCoverProvider):
    async def generate_cover(
        self,
        *,
        prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> CoverGenerationResult:
        request = httpx.Request("GET", SIGNED_FALLBACK_URL)
        response = httpx.Response(
            403,
            text=RAW_UPSTREAM_BODY,
            headers={"content-type": "text/plain", "request-id": "req_download_failed"},
            request=request,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise
        raise AssertionError("expected fallback download HTTPStatusError")


class _SensitiveValueErrorProvider(BaseCoverProvider):
    async def generate_cover(
        self,
        *,
        prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> CoverGenerationResult:
        raise ValueError(RAW_PROVIDER_EXCEPTION)


class _FailingCoverGenerationService(CoverGenerationService):
    def _build_provider(self, settings: Settings) -> BaseCoverProvider:
        return _SignedUrlFailingProvider()


class _ValueErrorCoverGenerationService(CoverGenerationService):
    def _build_provider(self, settings: Settings) -> BaseCoverProvider:
        return _SensitiveValueErrorProvider()


def _assert_no_sensitive_detail(value: str) -> None:
    assert "download-secret" not in value
    assert "download-token" not in value
    assert "private-fragment" not in value
    assert "X-Amz-Signature" not in value
    assert RAW_UPSTREAM_BODY not in value
    assert "body-secret" not in value
    assert RAW_PROVIDER_EXCEPTION not in value
    assert "raw-sensitive-provider-detail" not in value


async def test_generate_cover_http_status_error_does_not_leak_signed_url_or_raw_body(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    async_db_session: async_sessionmaker[AsyncSession],
) -> None:
    caplog.set_level("ERROR", logger="app.services.cover_generation_service")
    service = _FailingCoverGenerationService()

    async def fake_build_prompt(
        cls: type[PromptService],
        project: Project,
        user_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> str:
        return "safe prompt"

    monkeypatch.setattr(PromptService, "build_novel_cover_prompt", classmethod(fake_build_prompt))

    async with async_db_session() as db:
        project_id = "project-1"
        project = Project(id=project_id, user_id="user-1", title="Novel", cover_status="none")
        settings = Settings(
            user_id="user-1",
            cover_enabled=True,
            cover_api_provider="openai",
            cover_api_key="test-key",
            cover_image_model="gpt-image-2",
            cover_api_base_url="",
        )
        db.add_all([project, settings])
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.generate_cover(db=db, user_id="user-1", project_id=project_id)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "上游图片服务请求失败 (HTTP 403)"
        assert str(project.cover_status) == "failed"
        assert str(project.cover_error) == "上游图片服务请求失败 (HTTP 403)"
        _assert_no_sensitive_detail(str(exc_info.value.detail))
        _assert_no_sensitive_detail(str(project.cover_error))
        _assert_no_sensitive_detail(caplog.text)


async def test_generate_cover_generic_exception_does_not_leak_raw_error(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    async_db_session: async_sessionmaker[AsyncSession],
) -> None:
    caplog.set_level("ERROR", logger="app.services.cover_generation_service")
    service = _ValueErrorCoverGenerationService()

    async def fake_build_prompt(
        cls: type[PromptService],
        project: Project,
        user_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> str:
        return "safe prompt"

    monkeypatch.setattr(PromptService, "build_novel_cover_prompt", classmethod(fake_build_prompt))

    async with async_db_session() as db:
        project_id = "project-value-error"
        project = Project(id=project_id, user_id="user-1", title="Novel", cover_status="none")
        settings = Settings(
            user_id="user-1",
            cover_enabled=True,
            cover_api_provider="openai",
            cover_api_key="test-key",
            cover_image_model="gpt-image-2",
            cover_api_base_url="",
        )
        db.add_all([project, settings])
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.generate_cover(db=db, user_id="user-1", project_id=project_id)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == GENERIC_COVER_FAILURE
        assert str(project.cover_status) == "failed"
        assert str(project.cover_error) == GENERIC_COVER_FAILURE
        assert "exception_type=ValueError" in caplog.text
        _assert_no_sensitive_detail(str(exc_info.value.detail))
        _assert_no_sensitive_detail(str(project.cover_error))
        _assert_no_sensitive_detail(caplog.text)


def test_extract_upstream_error_detail_uses_generic_message_for_non_json_body() -> None:
    request = httpx.Request("GET", SIGNED_FALLBACK_URL)
    response = httpx.Response(
        502,
        text=RAW_UPSTREAM_BODY,
        headers={"content-type": "text/plain"},
        request=request,
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        response.raise_for_status()

    detail = CoverGenerationService._extract_upstream_error_detail(exc_info.value)

    assert detail == "上游图片服务请求失败 (HTTP 502)"
    _assert_no_sensitive_detail(detail)


def test_extract_upstream_error_detail_uses_generic_message_for_json_sensitive_detail() -> None:
    request = httpx.Request("GET", "https://api.example.test/images/generations")
    response = httpx.Response(
        400,
        json={"detail": RAW_JSON_ERROR_DETAIL},
        request=request,
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        response.raise_for_status()

    detail = CoverGenerationService._extract_upstream_error_detail(exc_info.value)

    assert detail == "上游图片服务请求失败 (HTTP 400)"
    assert "download-secret" not in detail
    assert "private-fragment" not in detail
    assert "raw-sensitive-provider-detail" not in detail


def test_http_status_error_log_fields_strip_userinfo_query_and_fragment() -> None:
    request = httpx.Request(
        "GET",
        "https://user:pass@example.test/cover.png?token=download-secret#private-fragment",
    )
    response = httpx.Response(401, request=request)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        response.raise_for_status()

    fields = CoverGenerationService._http_status_error_log_fields(exc_info.value)

    assert fields["request_url"] == "https://example.test/cover.png"
    log_text = str(fields)
    assert "user" not in log_text
    assert "pass" not in log_text
    assert "download-secret" not in log_text
    assert "private-fragment" not in log_text
    assert "token" not in log_text
