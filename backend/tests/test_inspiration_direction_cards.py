from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from types import SimpleNamespace
from typing import Any
from uuid import UUID
import json
import sys
import types

import pytest  # pyright: ignore[reportMissingImports]
import sqlalchemy as sa  # pyright: ignore[reportMissingImports]
from fastapi.testclient import TestClient  # pyright: ignore[reportMissingImports]
from sqlalchemy.orm import Session, sessionmaker  # pyright: ignore[reportMissingImports]
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

from app.api import inspiration  # pyright: ignore[reportImplicitRelativeImport]
from app.main import app  # pyright: ignore[reportImplicitRelativeImport]


USER_ID = "user-inspiration-direction-cards"


class FakeAIService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[str] = []

    def queue_json(self, payload: dict[str, Any]) -> None:
        self.responses.append(json.dumps(payload, ensure_ascii=False))

    def queue_text(self, content: str) -> None:
        self.responses.append(content)

    async def generate_text_stream(
        self,
        *,
        prompt: str,
        system_prompt: str,
        temperature: float,
        auto_mcp: bool = True,
        reasoning_intensity: str | None = None,
    ) -> AsyncIterator[str]:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "auto_mcp": auto_mcp,
                "reasoning_intensity": reasoning_intensity,
            }
        )
        assert self.responses, "测试没有预置AI响应"
        content = self.responses.pop(0)
        split_at = max(1, len(content) // 2)
        yield content[:split_at]
        yield content[split_at:]


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
        return SimpleNamespace(id=user_id, username="direction-card-user", trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator[Session]:
        with session_factory() as session:
            yield session

    async def fake_user_ai_service() -> FakeAIService:
        return fake_ai

    async def fake_get_template(template_key: str, user_id: str | None, db: object) -> str:
        _ = db
        assert user_id == USER_ID
        if template_key == "INSPIRATION_DIRECTION_CARDS":
            return "INSPIRATION_DIRECTION_CARDS | idea={idea}; context={context_json}; card_count={card_count}"
        if template_key == "INSPIRATION_MERGE_CARDS":
            return "INSPIRATION_MERGE_CARDS | cards={cards_json}; primary={primary_card_id}; instructions={instructions}"
        raise AssertionError(f"Unexpected template key: {template_key}")

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


def _direction_card(
    card_id: str,
    title: str | None = None,
    golden_finger: str | None = None,
) -> dict[str, Any]:
    card_suffix = card_id[-1]
    return {
        "id": card_id,
        "title": title or f"星桥方向{card_id[-1]}",
        "hook": f"断裂星桥后的归乡者必须在第{card_suffix}条航线用记忆支付代价。",
        "genre": ["科幻", "冒险"],
        "world_setting": "星桥税则限制远航，记忆是唯一燃料。",
        "core_conflict": "归乡者对抗垄断星桥的封锁联盟。",
        "protagonist": "失忆星图师，渴望找回故乡坐标。",
        "golden_finger": golden_finger,
        "opening_hook": "主角醒来时，最后一段童年记忆正在被拍卖。",
        "selling_points": ["记忆燃料", "星桥远航", "身份谜团"],
        "risks": ["规则过复杂", "情感线需要提前落点"],
    }


def _cards_payload(cards: list[dict[str, Any]], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "prompt": "我为这个创意准备了3个故事方向，请选择或组合：",
        "cards": cards,
        "warnings": warnings or [],
    }


def _assert_uuid(value: str) -> None:
    parsed = UUID(value)
    assert str(parsed) == value


def _structured_detail(payload: dict[str, Any]) -> dict[str, Any]:
    detail = payload["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == inspiration.INSPIRATION_STRUCTURED_OUTPUT_INVALID
    assert detail["error"] == inspiration.INSPIRATION_STRUCTURED_OUTPUT_INVALID
    return detail


def test_generate_cards_success_assigns_fresh_backend_uuids(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client
    source_cards = [
        _direction_card("ai_card_1"),
        _direction_card("ai_card_2", golden_finger="读取星桥残响"),
        _direction_card("ai_card_3", golden_finger=""),
    ]
    fake_ai.queue_json(_cards_payload(source_cards))

    response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "星桥断裂后的归乡故事", "context": {"genre": ["科幻"]}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"prompt", "cards", "warnings"}
    assert payload["prompt"] == "我为这个创意准备了3个故事方向，请选择或组合："
    assert payload["warnings"] == []
    assert len(payload["cards"]) == 3

    returned_ids = [card["id"] for card in payload["cards"]]
    assert len(set(returned_ids)) == 3
    for returned_id in returned_ids:
        _assert_uuid(returned_id)
        assert returned_id not in {card["id"] for card in source_cards}

    assert [card["title"] for card in payload["cards"]] == [card["title"] for card in source_cards]
    assert len(fake_ai.calls) == 1
    call = fake_ai.calls[0]
    assert call["temperature"] == pytest.approx(0.7)
    assert call["auto_mcp"] is False
    assert call["reasoning_intensity"] == "auto"
    assert "INSPIRATION_DIRECTION_CARDS" in call["system_prompt"]
    assert "星桥断裂后的归乡故事" in call["system_prompt"]
    assert "card_count=3" in call["system_prompt"]


def test_generate_cards_truncates_extra_valid_cards_with_warning(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client
    source_cards = [_direction_card(f"ai_card_{index}") for index in range(1, 5)]
    fake_ai.queue_json(_cards_payload(source_cards, warnings=["模型提示：第四张用于备选。"]))

    response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "星桥断裂后的归乡故事", "context": {}, "card_count": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["cards"]) == 3
    assert [card["title"] for card in payload["cards"]] == [card["title"] for card in source_cards[:3]]
    assert "星桥方向4" not in {card["title"] for card in payload["cards"]}
    assert "模型提示：第四张用于备选。" in payload["warnings"]
    assert any("截断" in warning and "4" in warning and "3" in warning for warning in payload["warnings"])
    for card in payload["cards"]:
        _assert_uuid(card["id"])
        assert card["id"] not in {source_card["id"] for source_card in source_cards}


def test_generate_cards_rejects_fewer_malformed_and_missing_required_fields(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    fake_ai.queue_json(_cards_payload([_direction_card("ai_card_1"), _direction_card("ai_card_2")]))
    fewer_response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "星桥断裂后的归乡故事", "context": {}},
    )
    assert fewer_response.status_code == 422
    fewer_detail = _structured_detail(fewer_response.json())
    assert fewer_detail["details"] == {"expected_count": 3, "actual_count": 2}

    fake_ai.queue_text("```json\n{bad json\n```")
    malformed_response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "星桥断裂后的归乡故事", "context": {}},
    )
    assert malformed_response.status_code == 422
    malformed_detail = _structured_detail(malformed_response.json())
    assert "JSON" in malformed_detail["message"]

    invalid_card = _direction_card("ai_card_bad")
    invalid_card.pop("core_conflict")
    fake_ai.queue_json(
        _cards_payload([invalid_card, _direction_card("ai_card_2"), _direction_card("ai_card_3")])
    )
    invalid_response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "星桥断裂后的归乡故事", "context": {}},
    )
    assert invalid_response.status_code == 422
    invalid_detail = _structured_detail(invalid_response.json())
    assert invalid_detail["details"]

    assert len(fake_ai.calls) == 3


def test_generate_cards_rejects_prose_and_duplicate_card_content(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client

    fake_ai.queue_text("这里是三个故事方向的说明，但没有返回JSON对象。")
    prose_response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "星桥断裂后的归乡故事", "context": {}},
    )
    assert prose_response.status_code == 422
    prose_detail = _structured_detail(prose_response.json())
    assert "JSON" in prose_detail["message"]

    duplicate_cards = [
        _direction_card("ai_card_1", title="星桥税吏"),
        _direction_card("ai_card_2", title="星桥税吏！"),
        _direction_card("ai_card_3", title="故乡坐标"),
    ]
    fake_ai.queue_json(_cards_payload(duplicate_cards))
    duplicate_response = client.post(
        "/api/inspiration/generate-cards",
        json={"idea": "星桥断裂后的归乡故事", "context": {}},
    )
    assert duplicate_response.status_code == 422
    duplicate_detail = _structured_detail(duplicate_response.json())
    assert "重复" in duplicate_detail["message"]
    assert duplicate_detail["details"]["field"] == "title"

    assert len(fake_ai.calls) == 2


def test_generate_cards_uses_session_user_scope_despite_client_user_id(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client
    fake_ai.queue_json(
        _cards_payload([
            _direction_card("ai_card_1"),
            _direction_card("ai_card_2"),
            _direction_card("ai_card_3"),
        ])
    )

    response = client.post(
        "/api/inspiration/generate-cards",
        json={
            "idea": "星桥断裂后的归乡故事",
            "context": {"user_id": "attacker-user", "genre": ["科幻"]},
        },
    )

    assert response.status_code == 200
    assert len(response.json()["cards"]) == 3
    assert len(fake_ai.calls) == 1
    assert "attacker-user" in fake_ai.calls[0]["system_prompt"]


def test_merge_cards_success_assigns_new_uuid_and_preserves_warnings(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client
    first_card = _direction_card("source_card_1", "记忆星桥")
    second_card = _direction_card("source_card_2", "月潮封锁")
    fake_ai.queue_json(
        {
            "card": _direction_card("source_card_1", "合并后的星桥方向", "读取星桥残响"),
            "warnings": ["已吸收第二张卡片的月潮卖点。"],
        }
    )

    response = client.post(
        "/api/inspiration/merge-cards",
        json={
            "cards": [first_card, second_card],
            "primary_card_id": "source_card_1",
            "instructions": "保留记忆燃料，并吸收月潮边界。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"card", "warnings"}
    assert payload["warnings"] == ["已吸收第二张卡片的月潮卖点。"]
    merged_card = payload["card"]
    _assert_uuid(merged_card["id"])
    assert merged_card["id"] not in {"source_card_1", "source_card_2"}
    assert merged_card["title"] == "合并后的星桥方向"

    assert len(fake_ai.calls) == 1
    call = fake_ai.calls[0]
    assert call["temperature"] == pytest.approx(0.6)
    assert call["auto_mcp"] is False
    assert call["reasoning_intensity"] == "auto"
    assert "INSPIRATION_MERGE_CARDS" in call["system_prompt"]
    assert "source_card_1" in call["system_prompt"]
    assert "保留记忆燃料" in call["system_prompt"]


def test_merge_cards_rejects_one_or_three_cards_before_ai_call(
    api_client: tuple[TestClient, FakeAIService],
) -> None:
    client, fake_ai = api_client
    cards = [
        _direction_card("source_card_1"),
        _direction_card("source_card_2"),
        _direction_card("source_card_3"),
    ]

    for invalid_cards in (cards[:1], cards):
        response = client.post(
            "/api/inspiration/merge-cards",
            json={"cards": invalid_cards, "instructions": "尝试合并"},
        )
        assert response.status_code == 400
        detail = _structured_detail(response.json())
        assert detail["details"] == {"expected_count": 2, "actual_count": len(invalid_cards)}

    assert fake_ai.calls == []
