from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
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


async def _cleanup_http_clients() -> None:
    return None


_ai_service_stub = types.ModuleType("app.services.ai_service")
setattr(_ai_service_stub, "AIService", _StubAIService)
setattr(_ai_service_stub, "create_user_ai_service", _create_stub_ai_service)
setattr(_ai_service_stub, "create_user_ai_service_with_mcp", _create_stub_ai_service)
setattr(_ai_service_stub, "normalize_provider", lambda provider: provider.lower().strip() if provider else None)
setattr(_ai_service_stub, "cleanup_http_clients", _cleanup_http_clients)
_ = sys.modules.setdefault("app.services.ai_service", _ai_service_stub)

from app.api import inspiration  # pyright: ignore[reportImplicitRelativeImport]
from app.main import app  # pyright: ignore[reportImplicitRelativeImport]


USER_ID = "user-inspiration-quality"


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
    ) -> AsyncIterator[str]:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
            }
        )
        assert self.responses, "测试没有预置AI响应"
        content = self.responses.pop(0)
        split_at = max(1, len(content) // 2)
        yield content[:split_at]
        yield content[split_at:]


@dataclass
class ApiHarness:
    client: TestClient
    fake_ai: FakeAIService
    count_rows: Callable[[], int]


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
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
        return SimpleNamespace(id=user_id, username="quality-user", trust_level=1, is_admin=False)

    async def override_get_db() -> AsyncIterator[Session]:
        with session_factory() as session:
            yield session

    async def fake_user_ai_service() -> FakeAIService:
        return fake_ai

    async def fake_get_template(template_key: str, user_id: str | None, db: object) -> str:
        _ = db
        assert user_id == USER_ID
        if template_key == "INSPIRATION_QUALITY_CHECK":
            return "INSPIRATION_QUALITY_CHECK | draft={draft_json}; context={context_json}"
        if template_key == "INSPIRATION_REPAIR":
            return "INSPIRATION_REPAIR | draft={draft_json}; issues={issues_json}; instructions={instructions}"
        raise AssertionError(f"Unexpected template key: {template_key}")

    def count_rows() -> int:
        with session_factory() as session:
            total = 0
            for table in Base.metadata.sorted_tables:
                total += session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            return int(total)

    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    monkeypatch.setattr(inspiration.PromptService, "get_template", staticmethod(fake_get_template))
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[inspiration.get_user_ai_service] = fake_user_ai_service

    client = TestClient(app)
    client.cookies.set("session_token", create_session_token(USER_ID, 3600))
    try:
        yield ApiHarness(client=client, fake_ai=fake_ai, count_rows=count_rows)
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def _story_bible(golden_finger: str | None = None) -> dict[str, Any]:
    return {
        "core_idea": "断裂星桥后的归乡故事",
        "story_promise": "每卷修复一段星桥，同时揭开主角被抹除的故乡真相。",
        "target_genre": ["科幻", "冒险"],
        "world_rules": ["记忆可作为燃料", "星桥航线需要税印", "月潮会改写城市边界"],
        "core_conflict": "主角必须在找回记忆和拯救同伴之间不断做选择。",
        "protagonist_profile": "失忆星图师，谨慎但无法拒绝求救。",
        "antagonistic_force": "垄断星桥税则的封锁联盟。",
        "golden_finger": golden_finger,
        "opening_hook": "主角的最后一段童年记忆被公开拍卖。",
        "tone_and_style": "奇观冒险与温暖群像并重。",
        "foreshadowing_seeds": ["破损罗盘", "无名税印", "反复出现的童谣"],
        "constraints": ["不使用全知旁白提前揭底", "每卷至少解决一个航线问题"],
    }


def _direction_card(golden_finger: str | None = None) -> dict[str, Any]:
    return {
        "id": "card-star-bridge",
        "title": "星桥税吏",
        "hook": "失忆星图师追回被星桥吞掉的故乡坐标。",
        "genre": ["科幻", "冒险"],
        "world_setting": "星桥税则限制远航，记忆是唯一燃料。",
        "core_conflict": "修复星桥需要牺牲故乡最后坐标。",
        "protagonist": "失忆星图师，谨慎但无法拒绝求救。",
        "golden_finger": golden_finger,
        "opening_hook": "主角醒来时，最后一段童年记忆正在被拍卖。",
        "selling_points": ["记忆燃料", "星桥远航", "身份谜团"],
        "risks": ["规则过复杂", "情感线需要提前落点"],
    }


def _quality_issue() -> dict[str, Any]:
    return {
        "id": "opening-hook-1",
        "dimension": "commercial_hook",
        "severity": "warning",
        "message": "第一章能力展示还可以更明确。",
        "suggestion": "在拍卖现场安排一次低成本解谜。",
    }


def _quality_report() -> dict[str, Any]:
    return {
        "overall_score": 86,
        "dimensions": {
            "novelty": 82,
            "writability": 88,
            "commercial_hook": 84,
            "consistency": 91,
            "long_form_potential": 87,
        },
        "issues": [_quality_issue()],
        "repair_suggestions": ["强化开篇行动目标"],
        "warnings": [],
    }


def test_evaluate_accepts_null_golden_finger_without_persistence(api_client: ApiHarness) -> None:
    assert api_client.count_rows() == 0
    api_client.fake_ai.queue_json(_quality_report())

    response = api_client.client.post(
        "/api/inspiration/evaluate",
        json={
            "story_bible_draft": _story_bible(None),
            "context": {"initial_idea": "星桥断裂后的归乡故事"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_score"] == 86
    assert payload["dimensions"]["commercial_hook"] == 84
    assert payload["issues"][0]["id"] == "opening-hook-1"
    assert api_client.count_rows() == 0

    assert len(api_client.fake_ai.calls) == 1
    call = api_client.fake_ai.calls[0]
    assert call["temperature"] == pytest.approx(0.35)
    assert "INSPIRATION_QUALITY_CHECK" in call["system_prompt"]
    assert '"golden_finger": null' in call["system_prompt"]


def test_repair_story_bible_once_and_does_not_persist(api_client: ApiHarness) -> None:
    repaired_draft = _story_bible(None)
    repaired_draft["opening_hook"] = "拍卖锤落下前，主角用破损罗盘破解了第一枚税印。"
    api_client.fake_ai.queue_json(
        {
            "repaired": True,
            "draft": repaired_draft,
            "remaining_issues": [],
            "warnings": ["仅强化开篇行动，不改变归乡核心前提。"],
        }
    )

    response = api_client.client.post(
        "/api/inspiration/repair",
        json={
            "draft": _story_bible(None),
            "issues": [_quality_issue()],
            "issue_ids": ["opening-hook-1"],
            "instructions": "只强化开篇钩子，不改核心创意。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repaired"] is True
    assert payload["draft"]["core_idea"] == "断裂星桥后的归乡故事"
    assert payload["draft"]["golden_finger"] is None
    assert payload["draft"]["opening_hook"] == "拍卖锤落下前，主角用破损罗盘破解了第一枚税印。"
    assert payload["remaining_issues"] == []
    assert api_client.count_rows() == 0

    assert len(api_client.fake_ai.calls) == 1
    call = api_client.fake_ai.calls[0]
    assert call["temperature"] == pytest.approx(0.45)
    assert "INSPIRATION_REPAIR" in call["system_prompt"]
    assert "opening-hook-1" in call["system_prompt"]
    assert "只强化开篇钩子" in call["system_prompt"]


def test_repair_validation_failure_returns_original_draft_and_remaining_issues(
    api_client: ApiHarness,
) -> None:
    original = _story_bible(None)
    api_client.fake_ai.queue_text("```json\n{bad json\n```")

    response = api_client.client.post(
        "/api/inspiration/repair",
        json={
            "draft": original,
            "issues": [_quality_issue()],
            "issue_ids": ["opening-hook-1"],
            "instructions": "修复开篇动作",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repaired"] is False
    assert payload["draft"] == original
    assert payload["remaining_issues"] == [_quality_issue()]
    assert "已保留原始草稿" in payload["warnings"][0]
    assert api_client.count_rows() == 0
    assert len(api_client.fake_ai.calls) == 1


def test_repair_rejects_type_swapped_output_and_keeps_original(api_client: ApiHarness) -> None:
    original = _story_bible(None)
    api_client.fake_ai.queue_json(
        {
            "repaired": True,
            "draft": _direction_card(None),
            "remaining_issues": [],
            "warnings": ["模型返回了方向卡片。"],
        }
    )

    response = api_client.client.post(
        "/api/inspiration/repair",
        json={
            "draft": original,
            "issues": [_quality_issue()],
            "issue_ids": ["opening-hook-1"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repaired"] is False
    assert payload["draft"] == original
    assert payload["remaining_issues"] == [_quality_issue()]
    assert "类型" in payload["warnings"][0]
    assert api_client.count_rows() == 0
    assert len(api_client.fake_ai.calls) == 1
