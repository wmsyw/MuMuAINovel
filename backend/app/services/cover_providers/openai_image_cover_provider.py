from __future__ import annotations

from typing import Final, assert_never

import httpx

from app.logger import get_logger
from app.services.cover_providers._openai_image_response import (
    Base64ImageData,
    OpenAIImagePayload,
    ParsedImageResponse,
    UrlImageData,
    guess_image_format,
    parse_image_response,
    response_log_fields,
)
from app.services.cover_providers._openai_image_url import resolve_public_image_url
from app.services.cover_providers.base_cover_provider import BaseCoverProvider, CoverGenerationResult

logger = get_logger(__name__)

DEFAULT_OPENAI_IMAGE_BASE_URL: Final = "https://api.openai.com/v1"


class OpenAIImageCoverProvider(BaseCoverProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_OPENAI_IMAGE_BASE_URL).rstrip("/")
        self._transport = transport

    async def generate_cover(
        self,
        *,
        prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> CoverGenerationResult:
        result = await self._request_cover(
            prompt=prompt,
            model=model,
            width=width,
            height=height,
        )
        return result

    async def _request_cover(
        self,
        *,
        prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> CoverGenerationResult:
        url = f"{self.base_url}/images/generations"
        log_url = str(
            httpx.URL(url).copy_with(username="", password="", query=None, fragment=None)
        )
        payload: OpenAIImagePayload = {
            "model": model,
            "prompt": self._adapt_prompt(prompt=prompt, width=width, height=height),
            "n": 1,
            "size": f"{width}x{height}",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(
            "OpenAI 图片封面生成请求开始: url=%s model=%s width=%s height=%s prompt_len=%s",
            log_url,
            model,
            width,
            height,
            len(prompt or ""),
        )

        async with httpx.AsyncClient(timeout=180.0, transport=self._transport) as client:
            response = await client.post(url, headers=headers, json=payload)

            logger.debug("OpenAI 图片封面生成响应: %s", response_log_fields(response))

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                fields = response_log_fields(exc.response, parse_body=True) if exc.response is not None else None
                logger.error("OpenAI 图片封面生成 HTTP 错误: %s", fields)
                raise

            parsed = parse_image_response(response)
            logger.debug(
                "OpenAI 图片封面生成解析结果: has_data=%s image_count=%s keys=%s response_fields=%s",
                bool(parsed.body_keys),
                parsed.image_count,
                list(parsed.body_keys),
                response_log_fields(response, parse_body=True),
            )

            logger.debug(
                "OpenAI 首张图片结果: keys=%s has_b64=%s has_url=%s revised_prompt_length=%s",
                list(parsed.first_image_keys),
                parsed.has_b64,
                parsed.has_url,
                parsed.revised_prompt_length,
            )
            return await self._resolve_image_data(client=client, parsed=parsed, model=model)

    async def _resolve_image_data(
        self,
        *,
        client: httpx.AsyncClient,
        parsed: ParsedImageResponse,
        model: str,
    ) -> CoverGenerationResult:
        match parsed.image:
            case Base64ImageData(content=content, image_format=image_format, revised_prompt=revised_prompt):
                logger.debug(
                    "OpenAI 返回 base64 图片: bytes=%s mime=%s extension=%s",
                    len(content),
                    image_format.mime_type,
                    image_format.file_extension,
                )
                return {
                    "content": content,
                    "mime_type": image_format.mime_type,
                    "file_extension": image_format.file_extension,
                    "revised_prompt": revised_prompt,
                    "provider": "openai",
                    "model": model,
                }
            case UrlImageData(url=image_url, revised_prompt=revised_prompt):
                return await self._download_url_image(
                    client=client,
                    image_url=image_url,
                    revised_prompt=revised_prompt,
                    model=model,
                )
            case unreachable:
                assert_never(unreachable)

    async def _download_url_image(
        self,
        *,
        client: httpx.AsyncClient,
        image_url: str,
        revised_prompt: str | None,
        model: str,
    ) -> CoverGenerationResult:
        pinned_url = resolve_public_image_url(image_url)
        logger.debug("OpenAI 兼容图片接口返回 URL，开始下载: url=%s", pinned_url.log_url)
        headers = {"Host": pinned_url.host_header} if pinned_url.host_header else None
        extensions = {"sni_hostname": pinned_url.sni_hostname} if pinned_url.sni_hostname else None
        response = await client.get(pinned_url.fetch_url, headers=headers, extensions=extensions)

        logger.debug("OpenAI 兼容图片下载响应: url=%s fields=%s", pinned_url.log_url, response_log_fields(response))
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            fields = response_log_fields(exc.response) if exc.response is not None else None
            logger.error("OpenAI 兼容图片下载 HTTP 错误: url=%s fields=%s", pinned_url.log_url, fields)
            raise

        image_format = guess_image_format(
            content=response.content,
            content_type=response.headers.get("content-type", ""),
            image_url=pinned_url.log_url,
        )
        return {
            "content": response.content,
            "mime_type": image_format.mime_type,
            "file_extension": image_format.file_extension,
            "revised_prompt": revised_prompt,
            "provider": "openai",
            "model": model,
        }

    @staticmethod
    def _adapt_prompt(*, prompt: str, width: int, height: int) -> str:
        cleaned_prompt = " ".join((prompt or "").split())
        return (
            f"{cleaned_prompt} "
            f"Use a {width}x{height} vertical book-cover composition."
        ).strip()
