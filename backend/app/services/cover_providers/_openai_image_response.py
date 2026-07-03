from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Final, TypeAlias, TypedDict

import httpx

REQUEST_ID_HEADERS: Final = ("x-request-id", "request-id", "openai-request-id", "openai-processing-ms")

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class OpenAIImagePayload(TypedDict):
    model: str
    prompt: str
    n: int
    size: str


class ResponseLogFields(TypedDict, total=False):
    status: int
    content_type: str | None
    request_ids: dict[str, str]
    body_type: str
    body_keys: list[str]
    error_type_present: bool
    error_code_present: bool
    error_type: str


@dataclass(frozen=True, slots=True)
class BodyNotProvided:
    pass


@dataclass(frozen=True, slots=True)
class ImageFormat:
    mime_type: str
    file_extension: str


@dataclass(frozen=True, slots=True)
class Base64ImageData:
    content: bytes
    image_format: ImageFormat
    revised_prompt: str | None


@dataclass(frozen=True, slots=True)
class UrlImageData:
    url: str
    revised_prompt: str | None


@dataclass(frozen=True, slots=True)
class ParsedImageResponse:
    image: Base64ImageData | UrlImageData
    body_keys: tuple[str, ...]
    image_count: int
    first_image_keys: tuple[str, ...]
    has_b64: bool
    has_url: bool
    revised_prompt_length: int


BODY_NOT_PROVIDED: Final = BodyNotProvided()


def parse_image_response(response: httpx.Response) -> ParsedImageResponse:
    data = json_object_from_response(response)
    images_value = data.get("data") or []
    image_count = len(images_value) if isinstance(images_value, list) else 0

    if not isinstance(images_value, list) or not images_value:
        raise ValueError("OpenAI 图片接口未返回图片结果")

    image_item = images_value[0]
    if not isinstance(image_item, dict):
        raise ValueError("OpenAI 图片接口返回的图片结果格式无效")

    revised_prompt = image_item.get("revised_prompt")
    revised_prompt_value = revised_prompt if isinstance(revised_prompt, str) else None
    b64_json = image_item.get("b64_json")
    image_url = image_item.get("url")
    image = _parse_image_item(
        b64_json=b64_json,
        image_url=image_url,
        revised_prompt=revised_prompt_value,
    )
    return ParsedImageResponse(
        image=image,
        body_keys=tuple(data.keys()),
        image_count=image_count,
        first_image_keys=tuple(str(key) for key in image_item.keys()),
        has_b64=isinstance(b64_json, str) and bool(b64_json.strip()),
        has_url=isinstance(image_url, str) and bool(image_url.strip()),
        revised_prompt_length=len(revised_prompt_value or ""),
    )


def json_object_from_response(response: httpx.Response) -> JsonObject:
    raw_data = response.json()
    if not isinstance(raw_data, dict):
        raise ValueError("OpenAI 图片接口返回格式无效")
    return {str(key): _to_json_value(value) for key, value in raw_data.items()}


def response_log_fields(
    response: httpx.Response,
    *,
    body: JsonObject | BodyNotProvided = BODY_NOT_PROVIDED,
    parse_body: bool = False,
) -> ResponseLogFields:
    content_type = response.headers.get("content-type")
    fields: ResponseLogFields = {
        "status": response.status_code,
        "content_type": content_type,
        "request_ids": {
            header: value
            for header in REQUEST_ID_HEADERS
            if (value := response.headers.get(header))
        },
    }

    if "json" not in (content_type or "").lower():
        fields["body_type"] = "non_json"
        return fields

    if isinstance(body, BodyNotProvided):
        if not parse_body:
            fields["body_type"] = "json_unparsed"
            return fields
        try:
            body = json_object_from_response(response)
        except ValueError:
            fields["body_type"] = "invalid_json"
            return fields

    fields["body_type"] = "object"
    fields["body_keys"] = sorted(body.keys())
    error_value = body.get("error")
    if isinstance(error_value, dict):
        error_type = error_value.get("type")
        error_code = error_value.get("code")
        if isinstance(error_type, str) and error_type.strip():
            fields["error_type_present"] = True
        if isinstance(error_code, str) and error_code.strip():
            fields["error_code_present"] = True
        if "error_type_present" not in fields and "error_code_present" not in fields:
            fields["error_type"] = "object"
    elif isinstance(error_value, str) and error_value.strip():
        fields["error_type"] = "string"
    return fields


def guess_image_format(
    *,
    content: bytes,
    content_type: str = "",
    image_url: str = "",
) -> ImageFormat:
    lowered_content_type = content_type.lower()
    lowered_url = image_url.lower()

    if content.startswith(b"\x89PNG\r\n\x1a\n") or "png" in lowered_content_type or lowered_url.endswith(".png"):
        return ImageFormat(mime_type="image/png", file_extension="png")
    if (
        content.startswith(b"\xff\xd8")
        or "jpeg" in lowered_content_type
        or "jpg" in lowered_content_type
        or lowered_url.endswith(".jpg")
        or lowered_url.endswith(".jpeg")
    ):
        return ImageFormat(mime_type="image/jpeg", file_extension="jpg")
    if (
        content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    ) or "webp" in lowered_content_type or lowered_url.endswith(".webp"):
        return ImageFormat(mime_type="image/webp", file_extension="webp")
    return ImageFormat(mime_type="image/png", file_extension="png")


def _parse_image_item(
    *,
    b64_json: JsonValue,
    image_url: JsonValue,
    revised_prompt: str | None,
) -> Base64ImageData | UrlImageData:
    if isinstance(b64_json, str) and b64_json.strip():
        decoded_content, data_url_content_type = _decode_base64_image(b64_json)
        return Base64ImageData(
            content=decoded_content,
            image_format=guess_image_format(content=decoded_content, content_type=data_url_content_type),
            revised_prompt=revised_prompt,
        )

    if isinstance(image_url, str) and image_url.strip():
        return UrlImageData(url=image_url, revised_prompt=revised_prompt)

    raise ValueError("OpenAI 图片接口未返回可用的图片数据")


def _decode_base64_image(value: str) -> tuple[bytes, str]:
    if value.startswith("data:") and "," in value:
        metadata, encoded = value.split(",", 1)
        content_type = metadata.removeprefix("data:").split(";", 1)[0]
        return base64.b64decode(encoded), content_type
    return base64.b64decode(value), ""


def _to_json_value(value) -> JsonValue:
    match value:
        case None | bool() | int() | float() | str():
            return value
        case list():
            return [_to_json_value(item) for item in value]
        case dict():
            return {str(key): _to_json_value(item) for key, item in value.items()}
        case _:
            return str(value)
