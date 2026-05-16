# pyright: reportMissingImports=false, reportImplicitRelativeImport=false, reportPrivateLocalImportUsage=false
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
# pyright: reportExplicitAny=false, reportUntypedFunctionDecorator=false, reportAny=false
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from types import SimpleNamespace
from typing import Any
import json
import sys
import types

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.middleware import auth_middleware
from app.security import create_session_token


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


def _normalize_provider(provider: str | None) -> str | None:
    return provider.lower().strip() if provider else None


async def _cleanup_http_clients() -> None:
    return None


_ai_service_stub = types.ModuleType("app.services.ai_service")
setattr(_ai_service_stub, "AIService", _StubAIService)
setattr(_ai_service_stub, "create_user_ai_service", _create_stub_ai_service)
setattr(_ai_service_stub, "create_user_ai_service_with_mcp", _create_stub_ai_service)
setattr(_ai_service_stub, "normalize_provider", _normalize_provider)
setattr(_ai_service_stub, "cleanup_http_clients", _cleanup_http_clients)
_ = sys.modules.setdefault("app.services.ai_service", _ai_service_stub)

from app.api import inspiration
from app.main import app


USER_ID = "user-inspiration-contract"

LEGACY_STEPS = ("title", "description", "theme", "genre")
SUPPORTED_STEPS = (
    "title",
    "description",
    "theme",
    "genre",
    "world_setting",
    "core_conflict",
    "protagonist",
    "golden_finger",
    "auto",
)

TEMPLATE_STEP_MARKERS = {
    "title": "INSPIRATION_TITLE_USER",
    "description": "INSPIRATION_DESCRIPTION_USER",
    "theme": "INSPIRATION_THEME_USER",
    "genre": "INSPIRATION_GENRE_USER",
    "world_setting": "INSPIRATION_WORLD_USER",
    "core_conflict": "INSPIRATION_CONFLICT_USER",
    "protagonist": "INSPIRATION_PROTAGONIST_USER",
    "golden_finger": "INSPIRATION_GOLDEN_FINGER_USER",
    "auto": "INSPIRATION_DYNAMIC_USER",
}

STEP_RESPONSES: dict[str, dict[str, Any]] = {
    "title": {
        "prompt": "请选择一个书名，或者输入你自己的：",
        "options": ["星桥尽头", "云城回声", "月潮归途"],
    },
    "description": {
        "prompt": "请选择一个简介，或者输入你自己的：",
        "options": [
            "断裂星桥后的远航者寻找归途。",
            "失落云城中，少女追寻旧日盟约。",
            "月潮回落前，众人必须修复裂隙。",
        ],
    },
    "theme": {
        "prompt": "请选择一个主题，或者输入你自己的：",
        "options": ["流亡与归属", "承诺与代价", "记忆与自由"],
    },
    "genre": {
        "prompt": "请选择类型标签（可多选）：",
        "options": ["科幻", "冒险", "悬疑"],
    },
    "world_setting": {
        "prompt": "请选择世界规则：",
        "options": ["星桥税则限制航行", "记忆可作为燃料", "月潮决定城市边界"],
    },
    "core_conflict": {
        "prompt": "请选择核心冲突：",
        "options": ["归乡者对抗封锁联盟", "记忆交易撕裂亲情", "修复星桥需要牺牲故乡"],
    },
    "protagonist": {
        "prompt": "请选择主角原型：",
        "options": ["失忆星图师", "逃亡修桥师", "背负旧约的领航员"],
    },
    "golden_finger": {
        "prompt": "请选择特殊优势：",
        "options": ["读取星桥残响", "短暂交换记忆", "无特殊金手指，仅保留普通优势"],
    },
    "auto": {
        "prompt": "请选择下一步灵感方向：",
        "options": ["强化世界规则", "深化人物代价", "放大商业钩子"],
    },
}

LEGACY_RESPONSES: dict[str, dict[str, Any]] = {
    step: STEP_RESPONSES[step]
    for step in LEGACY_STEPS
}

GENERATE_CONTEXTS: dict[str, dict[str, Any]] = {
    "title": {"initial_idea": "星桥断裂后的归乡故事", "description": "星桥断裂后的归乡故事"},
    "description": {"initial_idea": "星桥断裂后的归乡故事", "title": "星桥尽头"},
    "theme": {
        "initial_idea": "星桥断裂后的归乡故事",
        "title": "星桥尽头",
        "description": "断裂星桥后的远航者寻找归途。",
    },
    "genre": {
        "initial_idea": "星桥断裂后的归乡故事",
        "title": "星桥尽头",
        "description": "断裂星桥后的远航者寻找归途。",
        "theme": "流亡与归属",
    },
    "world_setting": {
        "initial_idea": "星桥断裂后的归乡故事",
        "title": "星桥尽头",
        "description": "断裂星桥后的远航者寻找归途。",
        "theme": "流亡与归属",
        "genre": ["科幻", "冒险"],
    },
    "core_conflict": {
        "initial_idea": "星桥断裂后的归乡故事",
        "title": "星桥尽头",
        "description": "断裂星桥后的远航者寻找归途。",
        "theme": "流亡与归属",
        "genre": ["科幻", "冒险"],
        "world_setting": "星桥税则限制航行",
    },
    "protagonist": {
        "initial_idea": "星桥断裂后的归乡故事",
        "title": "星桥尽头",
        "description": "断裂星桥后的远航者寻找归途。",
        "theme": "流亡与归属",
        "genre": ["科幻", "冒险"],
        "world_setting": "星桥税则限制航行",
        "core_conflict": "归乡者对抗封锁联盟",
    },
    "golden_finger": {
        "initial_idea": "星桥断裂后的归乡故事",
        "title": "星桥尽头",
        "description": "断裂星桥后的远航者寻找归途。",
        "theme": "流亡与归属",
        "genre": ["科幻", "冒险"],
        "world_setting": "星桥税则限制航行",
        "core_conflict": "归乡者对抗封锁联盟",
        "protagonist": "失忆星图师",
    },
    "auto": {
        "initial_idea": "星桥断裂后的归乡故事",
        "title": "星桥尽头",
        "description": "断裂星桥后的远航者寻找归途。",
        "theme": "流亡与归属",
        "genre": ["科幻", "冒险"],
        "world_setting": "星桥税则限制航行",
        "core_conflict": "归乡者对抗封锁联盟",
        "protagonist": "失忆星图师",
        "golden_finger": "读取星桥残响",
    },
}

GENERATE_TEMPERATURES = {
    "title": 0.8,
    "description": 0.65,
    "theme": 0.55,
    "genre": 0.45,
    "world_setting": 0.7,
    "core_conflict": 0.6,
    "protagonist": 0.65,
    "golden_finger": 0.75,
    "auto": 0.7,
}


class FakeAIService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate_text_stream(
        self,
        *,
        prompt: str,
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[str]:
        step = self._detect_step(prompt, system_prompt)
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "step": step,
            }
        )
        content = json.dumps(STEP_RESPONSES[step], ensure_ascii=False)
        split_at = len(content) // 2
        yield content[:split_at]
        yield content[split_at:]

    def _clean_json_response(self, content: str) -> str:
        return content

    @staticmethod
    def _detect_step(prompt: str, system_prompt: str) -> str:
        for step, marker in TEMPLATE_STEP_MARKERS.items():
            if marker in prompt or marker in system_prompt:
                return step
        raise AssertionError(f"未能从提示词识别灵感步骤: {prompt!r} / {system_prompt!r}")


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeAIService]]:
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    fake_ai = FakeAIService()
    previous_overrides = dict(app.dependency_overrides)

    async def fake_get_user(user_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=user_id, username="inspiration-user", trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator[Session]:
        with session_factory() as session:
            yield session

    async def fake_user_ai_service() -> FakeAIService:
        return fake_ai

    async def fake_get_template(template_key: str, user_id: str | None, db: object) -> str:
        _ = db
        assert user_id == USER_ID
        if template_key in {"INSPIRATION_DYNAMIC_SYSTEM", "INSPIRATION_DYNAMIC_USER"}:
            return f"{template_key} | context={{context_json}}"

        return (
            f"{template_key} | "
            "initial={initial_idea}; title={title}; description={description}; "
            "theme={theme}; genre={genre}; world={world_setting}; "
            "conflict={core_conflict}; protagonist={protagonist}; golden={golden_finger}"
        )

    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    monkeypatch.setattr(inspiration.PromptService, "get_template", staticmethod(fake_get_template))
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[inspiration.get_user_ai_service] = fake_user_ai_service

    client = TestClient(app)
    client.cookies.set("session_token", create_session_token(USER_ID, 3600))
    try:
        yield client, fake_ai
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def _assert_prompt_options_shape(payload: dict[str, Any], expected: dict[str, Any]) -> None:
    assert set(payload) == {"prompt", "options"}
    assert payload == expected
    assert isinstance(payload["prompt"], str)
    assert isinstance(payload["options"], list)
    assert len(payload["options"]) >= 3
    assert all(isinstance(option, str) and option for option in payload["options"])


def test_generate_options_legacy_steps_keep_prompt_options_shape(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    for step in LEGACY_STEPS:
        response = client.post(
            "/api/inspiration/generate-options",
            json={"step": step, "context": GENERATE_CONTEXTS[step]},
        )

        assert response.status_code == 200
        _assert_prompt_options_shape(response.json(), LEGACY_RESPONSES[step])

    assert [call["step"] for call in fake_ai.calls] == list(LEGACY_STEPS)
    for call in fake_ai.calls:
        step = call["step"]
        assert call["temperature"] == pytest.approx(GENERATE_TEMPERATURES[step])


def test_refine_options_legacy_steps_keep_prompt_options_shape_and_feedback_context(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    for step in LEGACY_STEPS:
        response = client.post(
            "/api/inspiration/refine-options",
            json={
                "step": step,
                "context": GENERATE_CONTEXTS[step],
                "feedback": "更偏向史诗感，但保持当前设定",
                "previous_options": LEGACY_RESPONSES[step]["options"],
            },
        )

        assert response.status_code == 200
        _assert_prompt_options_shape(response.json(), LEGACY_RESPONSES[step])

    assert [call["step"] for call in fake_ai.calls] == list(LEGACY_STEPS)
    for call in fake_ai.calls:
        step = call["step"]
        assert call["temperature"] == pytest.approx(min(GENERATE_TEMPERATURES[step] + 0.1, 0.9))
        assert "更偏向史诗感" in call["system_prompt"]
        for previous_option in LEGACY_RESPONSES[step]["options"]:
            assert previous_option in call["system_prompt"]


def test_generate_options_accepts_all_backend_supported_inspiration_steps(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    for step in SUPPORTED_STEPS:
        response = client.post(
            "/api/inspiration/generate-options",
            json={"step": step, "context": GENERATE_CONTEXTS[step]},
        )

        assert response.status_code == 200
        _assert_prompt_options_shape(response.json(), STEP_RESPONSES[step])

    assert [call["step"] for call in fake_ai.calls] == list(SUPPORTED_STEPS)
    for call in fake_ai.calls:
        step = call["step"]
        assert call["temperature"] == pytest.approx(GENERATE_TEMPERATURES[step])


def test_unknown_inspiration_step_is_rejected_before_ai_call(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    generate_response = client.post(
        "/api/inspiration/generate-options",
        json={"step": "character_sheet", "context": {"initial_idea": "星桥断裂"}},
    )
    refine_response = client.post(
        "/api/inspiration/refine-options",
        json={
            "step": "character_sheet",
            "context": {"initial_idea": "星桥断裂"},
            "feedback": "请改成角色卡",
            "previous_options": ["旧选项A", "旧选项B", "旧选项C"],
        },
    )

    for response in (generate_response, refine_response):
        assert 400 <= response.status_code < 500
        assert response.status_code != 500
        payload = response.json()
        assert payload.get("detail")

    assert fake_ai.calls == []
