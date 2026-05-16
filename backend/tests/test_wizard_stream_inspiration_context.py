from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from types import SimpleNamespace
from typing import Any
import asyncio
import json
import sys
import types

import pytest  # pyright: ignore[reportMissingImports]
from fastapi.testclient import TestClient  # pyright: ignore[reportMissingImports]
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # pyright: ignore[reportMissingImports]
from sqlalchemy.pool import StaticPool  # pyright: ignore[reportMissingImports]

from app.database import Base, get_db  # pyright: ignore[reportImplicitRelativeImport]
from app.middleware import auth_middleware  # pyright: ignore[reportImplicitRelativeImport]
from app.security import create_session_token  # pyright: ignore[reportImplicitRelativeImport]


class _StubMCPClient:
    async def cleanup(self) -> None:
        return None

    def __getattr__(self, _: str) -> Callable[..., Awaitable[bool]]:
        async def async_noop(*args: object, **kwargs: object) -> bool:
            _ = args
            _ = kwargs
            return False

        return async_noop


class _StubMCPPluginConfig:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


_mcp_stub = types.ModuleType("app.mcp")
setattr(_mcp_stub, "mcp_client", _StubMCPClient())
setattr(_mcp_stub, "MCPPluginConfig", _StubMCPPluginConfig)
setattr(_mcp_stub, "PluginStatus", SimpleNamespace(ACTIVE="active", ERROR="error"))
setattr(_mcp_stub, "register_status_sync", lambda: None)
_ = sys.modules.setdefault("app.mcp", _mcp_stub)

_memory_service_stub = types.ModuleType("app.services.memory_service")
setattr(_memory_service_stub, "memory_service", SimpleNamespace())
_ = sys.modules.setdefault("app.services.memory_service", _memory_service_stub)


class _StubEmailService:
    async def send_mail(self, **_: object) -> None:
        return None


_email_service_stub = types.ModuleType("app.services.email_service")
setattr(_email_service_stub, "email_service", _StubEmailService())
_ = sys.modules.setdefault("app.services.email_service", _email_service_stub)


class _StubAIService:
    pass


def _create_stub_ai_service(*args: object, **kwargs: object) -> _StubAIService:
    _ = args
    _ = kwargs
    return _StubAIService()


async def _cleanup_http_clients() -> None:
    return None


_ai_service_stub = types.ModuleType("app.services.ai_service")
setattr(_ai_service_stub, "AIService", _StubAIService)
setattr(_ai_service_stub, "create_user_ai_service", _create_stub_ai_service)
setattr(_ai_service_stub, "create_user_ai_service_with_mcp", _create_stub_ai_service)
setattr(_ai_service_stub, "normalize_provider", lambda provider: provider.lower().strip() if provider else None)
setattr(_ai_service_stub, "cleanup_http_clients", _cleanup_http_clients)
_ = sys.modules.setdefault("app.services.ai_service", _ai_service_stub)

_auto_character_stub = types.ModuleType("app.services.auto_character_service")
setattr(
    _auto_character_stub,
    "get_auto_character_service",
    lambda _service: SimpleNamespace(
        check_and_create_missing_characters=lambda **_kwargs: _async_result(
            {"created_count": 0, "created_characters": []}
        )
    ),
)
_ = sys.modules.setdefault("app.services.auto_character_service", _auto_character_stub)

_auto_organization_stub = types.ModuleType("app.services.auto_organization_service")
setattr(
    _auto_organization_stub,
    "get_auto_organization_service",
    lambda _service: SimpleNamespace(
        check_and_create_missing_organizations=lambda **_kwargs: _async_result(
            {"created_count": 0, "created_organizations": []}
        )
    ),
)
_ = sys.modules.setdefault("app.services.auto_organization_service", _auto_organization_stub)

from app.api import wizard_stream  # pyright: ignore[reportImplicitRelativeImport]
from app.main import app  # pyright: ignore[reportImplicitRelativeImport]


USER_ID = "user-wizard-inspiration-context"
EXPECTED_EVENTS = ["start", "generating", "parsing", "saving", "complete", "result", "done"]


async def _async_result(value: dict[str, Any]) -> dict[str, Any]:
    return value


class FakeAIService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[str] = []

    def queue_json(self, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.responses.append(json.dumps(payload, ensure_ascii=False))

    def _clean_json_response(self, text: str) -> str:
        return text.strip().removeprefix("```json").removesuffix("```").strip()

    async def generate_text_stream(
        self,
        *,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[str]:
        self.calls.append(
            {
                "prompt": prompt,
                "provider": provider,
                "model": model,
                "tool_choice": tool_choice,
            }
        )
        assert self.responses, "测试没有预置AI响应"
        content = self.responses.pop(0)
        split_at = max(1, len(content) // 2)
        yield content[:split_at]
        yield content[split_at:]


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeAIService]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    fake_ai = FakeAIService()
    previous_overrides = dict(app.dependency_overrides)

    async def init_db() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def dispose_db() -> None:
        await engine.dispose()

    async def fake_get_user(user_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=user_id, username="wizard-context-user", trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator[Any]:
        async with session_factory() as session:
            yield session

    async def fake_user_ai_service() -> FakeAIService:
        return fake_ai

    async def fake_get_template(template_key: str, user_id: str | None, db: object) -> str:
        _ = db
        assert user_id == USER_ID
        if template_key == "WORLD_BUILDING":
            return "WORLD_BUILDING | title={title}; theme={theme}; genre={genre}; description={description}"
        if template_key == "OUTLINE_CREATE":
            return (
                "OUTLINE_CREATE | title={title}; theme={theme}; genre={genre}; chapter_count={chapter_count}; "
                "narrative={narrative_perspective}; target={target_words}; time={time_period}; location={location}; "
                "atmosphere={atmosphere}; rules={rules}; characters={characters_info}; requirements={requirements}"
            )
        raise AssertionError(f"Unexpected template key: {template_key}")

    asyncio.run(init_db())
    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    monkeypatch.setattr(wizard_stream.PromptService, "get_template", staticmethod(fake_get_template))
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[wizard_stream.get_user_ai_service] = fake_user_ai_service

    client = TestClient(app)
    client.cookies.set("session_token", create_session_token(USER_ID, 3600))
    try:
        yield client, fake_ai
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        asyncio.run(dispose_db())


def _story_bible() -> dict[str, Any]:
    return {
        "core_idea": "断裂星桥后的归乡故事",
        "story_promise": "每卷修复一段星桥，同时揭开故乡真相。",
        "target_genre": ["科幻", "冒险"],
        "world_rules": ["记忆可作为燃料", "星桥航线需要税印"],
        "core_conflict": "主角必须在找回记忆和拯救同伴之间做选择。",
        "protagonist_profile": "失忆星图师，谨慎但无法拒绝求救。",
        "antagonistic_force": "垄断星桥税则的封锁联盟。",
        "golden_finger": "读取星桥残响",
        "opening_hook": "主角的最后一段童年记忆被公开拍卖。",
        "tone_and_style": "奇观冒险与温暖群像并重。",
        "foreshadowing_seeds": ["破损罗盘", "无名税印"],
        "constraints": ["不提前揭底", "每卷解决一个航线问题"],
    }


def _inspiration_context() -> dict[str, Any]:
    return {
        "source": "inspiration_story_bible",
        "initial_idea": "星桥断裂后的归乡故事",
        "confirmed_fields": {
            "title": "星桥尽头",
            "world_setting": "星桥税则限制航行，记忆可作为燃料。",
        },
        "story_bible_draft": _story_bible(),
    }


def _world_payload(**extra: Any) -> dict[str, Any]:
    return {
        "title": "星桥尽头",
        "description": "远航者在星桥断裂后寻找归途。",
        "theme": "流亡与归属",
        "genre": "科幻、冒险",
        "narrative_perspective": "第三人称",
        "target_words": 100000,
        "chapter_count": 3,
        "character_count": 5,
        "outline_mode": "one-to-many",
        **extra,
    }


def _world_result() -> dict[str, Any]:
    return {
        "time_period": "星桥纪元",
        "location": "断裂星桥",
        "atmosphere": "浪漫冒险",
        "rules": "记忆可作为燃料，星桥航线需要税印。",
    }


def _outline_result() -> list[dict[str, Any]]:
    return [
        {"title": "记忆拍卖", "summary": "主角发现童年记忆被公开拍卖。", "characters": []},
        {"title": "税印追踪", "summary": "星桥税则暴露归乡代价。", "characters": []},
        {"title": "残响起航", "summary": "主角选择读取星桥残响。", "characters": []},
    ]


def _sse_payloads(text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line.removeprefix("data: ")))
    return payloads


def _event_names(text: str) -> list[str]:
    names: list[str] = []
    for payload in _sse_payloads(text):
        payload_type = payload.get("type")
        if payload_type == "progress":
            progress = payload.get("progress")
            progress_value = int(progress) if isinstance(progress, int | float | str) else -1
            message = str(payload.get("message", ""))
            status = payload.get("status")
            if progress == 0:
                name = "start"
            elif progress == 100 and status == "success":
                name = "complete"
            elif 85 <= progress_value <= 92 or "解析" in message:
                name = "parsing"
            elif 92 <= progress_value < 100 or "保存" in message or "校验" in message:
                name = "saving"
            elif "生成" in message:
                name = "generating"
            else:
                continue
        elif payload_type in {"result", "done"}:
            name = str(payload_type)
        else:
            continue

        if name not in names:
            names.append(name)
    return names


def _project_id(text: str) -> str:
    for payload in _sse_payloads(text):
        if payload.get("type") == "result":
            data = payload.get("data", {})
            if isinstance(data, dict) and data.get("project_id"):
                return str(data["project_id"])
    raise AssertionError("SSE result did not include project_id")


def test_wizard_stream_story_bible_context_is_prompt_only_and_preserves_legacy_sse_events(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client
    fake_ai.queue_json(_world_result())
    fake_ai.queue_json(_world_result())
    fake_ai.queue_json(_outline_result())
    fake_ai.queue_json(_outline_result())

    legacy_response = client.post("/api/wizard-stream/world-building", json=_world_payload())
    assert legacy_response.status_code == 200
    assert _event_names(legacy_response.text) == EXPECTED_EVENTS
    legacy_project_id = _project_id(legacy_response.text)

    context_response = client.post(
        "/api/wizard-stream/world-building",
        json=_world_payload(inspiration_context=_inspiration_context()),
    )
    assert context_response.status_code == 200
    assert _event_names(context_response.text) == EXPECTED_EVENTS
    context_project_id = _project_id(context_response.text)

    legacy_outline_response = client.post(
        "/api/wizard-stream/outline",
        json={
            "project_id": legacy_project_id,
            "chapter_count": 3,
            "narrative_perspective": "第三人称",
            "target_words": 100000,
        },
    )
    assert legacy_outline_response.status_code == 200
    assert _event_names(legacy_outline_response.text) == EXPECTED_EVENTS

    outline_response = client.post(
        "/api/wizard-stream/outline",
        json={
            "project_id": context_project_id,
            "chapter_count": 3,
            "narrative_perspective": "第三人称",
            "target_words": 100000,
            "inspiration_context": _inspiration_context(),
        },
    )
    assert outline_response.status_code == 200
    assert _event_names(outline_response.text) == EXPECTED_EVENTS

    assert len(fake_ai.calls) == 4
    legacy_world_prompt = fake_ai.calls[0]["prompt"]
    context_world_prompt = fake_ai.calls[1]["prompt"]
    legacy_outline_prompt = fake_ai.calls[2]["prompt"]
    context_outline_prompt = fake_ai.calls[3]["prompt"]
    assert "灵感模式故事圣经草稿" not in legacy_world_prompt
    assert "灵感模式故事圣经草稿" not in legacy_outline_prompt
    assert "灵感模式故事圣经草稿" in context_world_prompt
    assert "断裂星桥后的归乡故事" in context_world_prompt
    assert "读取星桥残响" in context_world_prompt
    assert "灵感模式故事圣经草稿" in context_outline_prompt
    assert "断裂星桥后的归乡故事" in context_outline_prompt
    assert "读取星桥残响" in context_outline_prompt
    assert "不代表已写入项目规范数据" in context_outline_prompt
