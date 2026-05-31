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
    "direction_cards": "INSPIRATION_DIRECTION_CARDS",
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

DIRECTION_CARDS_RESPONSE: dict[str, Any] = {
    "prompt": "请选择一个故事方向继续深化：",
    "cards": [
        {
            "id": "direction-card-1",
            "title": "废脉少年夺天梯",
            "hook": "被逐出宗门的少年在禁地拾回失传星骨。",
            "genre": ["玄幻", "逆袭"],
            "world_setting": "宗门用天梯排名分配灵脉与资源。",
            "core_conflict": "主角必须打破天梯垄断才能救回族人。",
            "protagonist": "外表废脉、擅长拆解阵法的少年。",
            "golden_finger": "能听见失传星骨中的古老阵音。",
            "opening_hook": "他在逐出仪式上当众粉碎了自己的废脉判书。",
            "selling_points": ["强逆袭爽点", "宗门阶层压迫", "阵法解谜升级"],
            "risks": ["需避免套路化", "升级节奏要稳定"],
        },
        {
            "id": "direction-card-2",
            "title": "云海镖师护仙种",
            "hook": "落魄镖师接下最后一趟镖，货物竟是会说话的仙种。",
            "genre": ["仙侠", "冒险"],
            "world_setting": "云海诸城靠浮舟贸易维系灵气循环。",
            "core_conflict": "各派追杀仙种，主角要在利益与守护间选择。",
            "protagonist": "讲义气但债务缠身的青年镖师。",
            "golden_finger": "仙种能预告三息后的危险。",
            "opening_hook": "第一章镖箱破裂，里面伸出一截发光嫩芽喊他爹。",
            "selling_points": ["公路冒险感", "轻喜剧互动", "阵营追逐"],
            "risks": ["设定解释不能过重", "萌点需服务主线"],
        },
        {
            "id": "direction-card-3",
            "title": "归墟书吏改命簿",
            "hook": "小书吏发现自己的名字每天都会在命簿上死一次。",
            "genre": ["奇幻", "悬疑"],
            "world_setting": "归墟城所有人的寿命都由命簿司登记。",
            "core_conflict": "主角调查命簿篡改者，却发现自己也是被创造的记录。",
            "protagonist": "谨慎、记忆力惊人的底层书吏。",
            "golden_finger": "能在墨迹干透前改写一行命簿。",
            "opening_hook": "他清晨点卯时，看见自己的死期写着昨天。",
            "selling_points": ["命运悬疑", "规则系能力", "身份反转"],
            "risks": ["规则要清晰", "反转伏笔需提前埋设"],
        },
    ],
    "warnings": [],
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
        response_payload = (
            DIRECTION_CARDS_RESPONSE
            if step == "direction_cards"
            else STEP_RESPONSES[step]
        )
        content = json.dumps(response_payload, ensure_ascii=False)
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
        if template_key == "INSPIRATION_DIRECTION_CARDS":
            return f"{template_key} | idea={{idea}}; context={{context_json}}; card_count={{card_count}}"

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


def _assert_direction_cards_shape(payload: dict[str, Any], expected_count: int = 3) -> None:
    assert set(payload) == {"prompt", "cards", "warnings"}
    assert isinstance(payload["prompt"], str)
    assert payload["prompt"]
    assert isinstance(payload["cards"], list)
    assert len(payload["cards"]) == expected_count
    assert isinstance(payload["warnings"], list)
    required_card_fields = {
        "id",
        "title",
        "hook",
        "genre",
        "world_setting",
        "core_conflict",
        "protagonist",
        "opening_hook",
        "selling_points",
        "risks",
    }
    for card in payload["cards"]:
        assert required_card_fields.issubset(card)
        assert isinstance(card["id"], str) and card["id"]
        assert isinstance(card["title"], str) and card["title"]
        assert isinstance(card["hook"], str) and card["hook"]
        assert isinstance(card["genre"], list) and card["genre"]
        assert all(isinstance(item, str) and item for item in card["genre"])
        assert isinstance(card["world_setting"], str) and card["world_setting"]
        assert isinstance(card["core_conflict"], str) and card["core_conflict"]
        assert isinstance(card["protagonist"], str) and card["protagonist"]
        assert card.get("golden_finger") is None or isinstance(card.get("golden_finger"), str)
        assert isinstance(card["opening_hook"], str) and card["opening_hook"]
        assert isinstance(card["selling_points"], list) and card["selling_points"]
        assert all(isinstance(item, str) and item for item in card["selling_points"])
        assert isinstance(card["risks"], list) and card["risks"]
        assert all(isinstance(item, str) and item for item in card["risks"])


def _extract_guidance_value(prompt: str, label: str) -> str:
    marker = f"{label}："
    for line in prompt.splitlines():
        if marker in line:
            return line.split(marker, 1)[1].strip()
    raise AssertionError(f"提示词缺少 {label}: {prompt}")


def _extract_guidance_items(prompt: str, label: str) -> list[str]:
    value = _extract_guidance_value(prompt, label)
    return [item.strip() for item in value.split("、") if item.strip()]


def test_generate_cards_guidance_request_accepts_and_legacy_idea_only_still_works(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    legacy_response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "一个修仙少年逆袭"},
    )
    assert legacy_response.status_code == 200, legacy_response.text
    _assert_direction_cards_shape(legacy_response.json())

    guidance_response = client.post(
        "/api/inspiration/generate-cards",
        json={
            "idea": "一个修仙少年逆袭",
            "guidance": {
                "channel": "男频",
                "genre": "玄幻",
                "themes": ["逆袭", "成长"],
                "characters": ["废柴少年", "隐世师父"],
                "plots": ["宗门试炼", "越级挑战"],
                "plot_brief": "少年在宗门压迫中觉醒失传阵法。",
            },
        },
    )
    assert guidance_response.status_code == 200, guidance_response.text
    _assert_direction_cards_shape(guidance_response.json())

    assert [call["step"] for call in fake_ai.calls] == ["direction_cards", "direction_cards"]
    legacy_prompt = fake_ai.calls[0]["system_prompt"]
    guidance_prompt = fake_ai.calls[1]["system_prompt"]
    assert "一个修仙少年逆袭" in legacy_prompt
    assert "灵感引导" not in legacy_prompt
    assert "基于这些灵感标签创作故事" not in legacy_prompt
    assert "灵感引导" in guidance_prompt
    assert "题材频道：男频" in guidance_prompt
    assert "类型标签：玄幻" in guidance_prompt
    assert "主题标签：逆袭、成长" in guidance_prompt
    assert "角色标签：废柴少年、隐世师父" in guidance_prompt
    assert "情节标签：宗门试炼、越级挑战" in guidance_prompt
    assert "剧情简述：少年在宗门压迫中觉醒失传阵法。" in guidance_prompt


def test_generate_cards_guidance_only_request_succeeds(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    response = client.post(
        "/api/inspiration/generate-cards",
        json={
            "guidance": {
                "channel": "女频",
                "genre": "奇幻",
                "themes": ["治愈", "成长"],
                "plots": ["学院入学"],
                "plot_brief": "失去魔法的少女在学院重新找到自我。",
            }
        },
    )

    assert response.status_code == 200, response.text
    _assert_direction_cards_shape(response.json())
    assert fake_ai.calls[-1]["step"] == "direction_cards"
    system_prompt = fake_ai.calls[-1]["system_prompt"]
    assert "女频" in system_prompt
    assert "奇幻" in system_prompt
    assert "失去魔法的少女" in system_prompt


def test_generate_cards_tags_only_without_idea_or_plot_brief_succeeds(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    response = client.post(
        "/api/inspiration/generate-cards",
        json={
            "guidance": {
                "channel": "男频",
                "genre": "玄幻",
                "themes": ["逆袭", "热血"],
                "characters": ["废柴少年"],
                "plots": ["宗门试炼"],
            }
        },
    )

    assert response.status_code == 200, response.text
    _assert_direction_cards_shape(response.json())
    assert fake_ai.calls[-1]["step"] == "direction_cards"
    system_prompt = fake_ai.calls[-1]["system_prompt"]
    assert "基于这些灵感标签创作故事" in system_prompt
    assert "男频频道" in system_prompt
    assert "主题逆袭、热血" in system_prompt
    assert "情节宗门试炼" in system_prompt
    assert "剧情简述" not in system_prompt
    assert "题材频道：男频" in system_prompt
    assert "类型标签：玄幻" in system_prompt
    assert "主题标签：逆袭、热血" in system_prompt
    assert "角色标签：废柴少年" in system_prompt
    assert "情节标签：宗门试炼" in system_prompt


def test_generate_cards_guidance_sanitizes_oversized_tags_before_ai_call(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client
    long_tag = "超长标签" * 20
    long_brief = "剧情" * 1000

    response = client.post(
        "/api/inspiration/generate-cards",
        json={
            "idea": "一个需要防御性清洗的灵感",
            "guidance": {
                "channel": " 男频 ",
                "genre": " 玄幻 ",
                "themes": [" 复仇 ", "", "   ", long_tag, "成长", "权谋", "群像", "爽文", "空串后应被丢弃"],
                "characters": [" 主角 ", "", long_tag, "师父", "宿敌", "伙伴", "反派", "路人"],
                "plots": [" 开局退婚 ", " ", long_tag, "秘境探索", "宗门大比", "最终决战", "飞升", "番外"],
                "plot_brief": long_brief,
            },
        },
    )

    assert response.status_code == 200, response.text
    system_prompt = fake_ai.calls[-1]["system_prompt"]
    for label in ("主题标签", "角色标签", "情节标签"):
        items = _extract_guidance_items(system_prompt, label)
        assert len(items) <= 5
        assert all(item for item in items)
        assert all(len(item) <= 30 for item in items)

    assert _extract_guidance_items(system_prompt, "主题标签")[0] == "复仇"
    assert _extract_guidance_items(system_prompt, "角色标签")[0] == "主角"
    assert _extract_guidance_items(system_prompt, "情节标签")[0] == "开局退婚"
    assert long_tag[:30] in _extract_guidance_items(system_prompt, "主题标签")
    assert len(_extract_guidance_value(system_prompt, "剧情简述")) <= 500


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
