from __future__ import annotations

import base64
import json
import socket

import httpx
import pytest
from fastapi import HTTPException

from app.services.cover_providers.openai_image_cover_provider import OpenAIImageCoverProvider

pytestmark = pytest.mark.anyio

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\xe8\x89"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_generate_cover_posts_openai_image_payload_and_decodes_png() -> None:
    captured_requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(PNG_1X1).decode("ascii"),
                        "revised_prompt": "revised cover prompt",
                    }
                ]
            },
        )

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_cover(
        prompt="A quiet mountain library",
        model="gpt-image-2",
        width=1024,
        height=1536,
    )

    assert result["content"] == PNG_1X1
    assert result["file_extension"] == "png"
    assert result["mime_type"] == "image/png"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-image-2"
    assert result["revised_prompt"] == "revised cover prompt"

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert str(request.url) == "https://api.openai.com/v1/images/generations"
    assert request.headers["authorization"] == "Bearer test-openai-key"
    payload = json.loads(request.content)
    assert payload["model"] == "gpt-image-2"
    assert payload["n"] == 1
    assert payload["size"] == "1024x1536"
    assert "A quiet mountain library" in payload["prompt"]
    assert "aspect_ratio" not in payload
    assert "resolution" not in payload
    assert "response_format" not in payload


async def test_generate_cover_request_start_log_sanitizes_base_url_query_and_fragment(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG", logger="app.services.cover_providers.openai_image_cover_provider")
    captured_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(PNG_1X1).decode("ascii")}]},
        )

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://api.example.test/v1?token=query-secret#fragment-secret",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_cover(
        prompt="A quiet mountain library",
        model="gpt-image-2",
        width=1024,
        height=1536,
    )

    assert result["content"] == PNG_1X1
    assert captured_urls == [
        "https://api.example.test/v1?token=query-secret#fragment-secret/images/generations"
    ]
    assert "OpenAI 图片封面生成请求开始" in caplog.text
    assert "https://api.example.test/v1" in caplog.text
    assert "query-secret" not in caplog.text
    assert "fragment-secret" not in caplog.text
    assert "?token" not in caplog.text
    assert "test-openai-key" not in caplog.text


async def test_generate_cover_decodes_base64_data_url_png() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": f"data:image/png;base64,{base64.b64encode(PNG_1X1).decode('ascii')}"}]},
        )

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_cover(
        prompt="A cover",
        model="gpt-image-2",
        width=1024,
        height=1536,
    )

    assert result["content"] == PNG_1X1
    assert result["file_extension"] == "png"


async def test_generate_cover_downloads_url_fallback_for_compatible_gateways() -> None:
    webp_bytes = b"RIFF\x0c\x00\x00\x00WEBPVP8 "
    captured_urls: list[str] = []
    public_image_url = "http://93.184.216.34/cover.webp"

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        if request.url.host == "93.184.216.34":
            return httpx.Response(200, content=webp_bytes, headers={"content-type": "image/webp"})
        return httpx.Response(200, json={"data": [{"url": public_image_url}]})

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://gateway.example.test/v1",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_cover(
        prompt="A cover",
        model="gpt-image-2",
        width=1024,
        height=1536,
    )

    assert captured_urls == [
        "https://gateway.example.test/v1/images/generations",
        public_image_url,
    ]
    assert result["content"] == webp_bytes
    assert result["file_extension"] == "webp"


async def test_generate_cover_url_fallback_pins_resolved_host_to_prevent_dns_rebinding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webp_bytes = b"RIFF\x0c\x00\x00\x00WEBPVP8 "
    public_image_url = "https://cdn.example.test/cover.webp?token=download-secret#private-fragment"
    captured_requests: list[httpx.Request] = []

    def fake_getaddrinfo(
        host: str,
        port: int,
        *args,
        **kwargs,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        assert host == "cdn.example.test"
        assert port == 443
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.host == "cdn.example.test":
            pytest.fail("fallback URL was fetched by hostname instead of the validated public IP")
        if request.url.host == "93.184.216.34":
            return httpx.Response(200, content=webp_bytes, headers={"content-type": "image/webp"})
        return httpx.Response(200, json={"data": [{"url": public_image_url}]})

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://gateway.example.test/v1",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_cover(
        prompt="A cover",
        model="gpt-image-2",
        width=1024,
        height=1536,
    )

    download_request = captured_requests[1]
    assert str(download_request.url) == "https://93.184.216.34/cover.webp?token=download-secret"
    assert download_request.headers["host"] == "cdn.example.test"
    assert download_request.extensions["sni_hostname"] == "cdn.example.test"
    assert result["content"] == webp_bytes
    assert result["file_extension"] == "webp"


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials",
        "http://127.0.0.1/cover.png",
        "http://localhost/cover.png",
        "http://100.64.0.1/cover.png",
    ],
)
async def test_generate_cover_rejects_non_global_url_fallback_before_fetch(blocked_url: str) -> None:
    captured_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        if str(request.url) == blocked_url:
            pytest.fail("blocked fallback URL was fetched")
        return httpx.Response(200, json={"data": [{"url": blocked_url}]})

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://gateway.example.test/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(HTTPException):
        await provider.generate_cover(
            prompt="A cover",
            model="gpt-image-2",
            width=1024,
            height=1536,
        )

    assert captured_urls == ["https://gateway.example.test/v1/images/generations"]


async def test_generate_cover_empty_data_raises_useful_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="OpenAI.*未返回图片结果"):
        await provider.generate_cover(
            prompt="A cover",
            model="gpt-image-2",
            width=1024,
            height=1536,
        )


async def test_generate_cover_generation_http_status_error_propagates(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG", logger="app.services.cover_providers.openai_image_cover_provider")

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "type": "raw-sensitive-provider-detail token=download-secret",
                    "code": "raw-sensitive-code token=download-secret",
                    "message": "raw-sensitive-provider-detail",
                }
            },
            headers={"x-request-id": "req_generation_failed"},
        )

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.generate_cover(
            prompt="A cover",
            model="gpt-image-2",
            width=1024,
            height=1536,
        )

    assert exc_info.value.response.status_code == 429
    assert "error_type_present" in caplog.text
    assert "error_code_present" in caplog.text
    assert "raw-sensitive-provider-detail" not in caplog.text
    assert "raw-sensitive-code" not in caplog.text
    assert "download-secret" not in caplog.text


async def test_generate_cover_url_fallback_http_status_error_propagates(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG", logger="app.services.cover_providers.openai_image_cover_provider")
    fallback_url = "http://93.184.216.34/cover.webp?token=download-secret#private-fragment"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "93.184.216.34":
            return httpx.Response(
                403,
                content=b"raw-sensitive-download-error",
                headers={"content-type": "text/plain", "request-id": "req_download_failed"},
            )
        return httpx.Response(200, json={"data": [{"url": fallback_url}]})

    provider = OpenAIImageCoverProvider(
        api_key="test-openai-key",
        base_url="https://gateway.example.test/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.generate_cover(
            prompt="A cover",
            model="gpt-image-2",
            width=1024,
            height=1536,
        )

    assert exc_info.value.response.status_code == 403
    assert "http://93.184.216.34/cover.webp" in caplog.text
    assert "download-secret" not in caplog.text
    assert "private-fragment" not in caplog.text
    assert "raw-sensitive-download-error" not in caplog.text
