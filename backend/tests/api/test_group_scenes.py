from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportAny=false, reportExplicitAny=false

import sys
import types

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Character, GroupScene, LorebookEntry, Project, VoicePersona


DEFAULT_TEST_PROJECT_ID = "project-test-default"
DEFAULT_TEST_USER_ID = "user-test-default"
OTHER_PROJECT_ID = "project-group-scene-other"
CHARACTER_A_ID = "character-group-scene-a"
CHARACTER_B_ID = "character-group-scene-b"
OTHER_CHARACTER_ID = "character-group-scene-other"
VOICE_PERSONA_ID = "voice-persona-group-scene"
LORE_ID = "lore-group-scene-court"


if "mcp" not in sys.modules:
    _mcp_stub = types.ModuleType("mcp")
    setattr(_mcp_stub, "ClientSession", type("ClientSession", (), {}))
    setattr(_mcp_stub, "types", types.SimpleNamespace(TextContent=type("TextContent", (), {}), ImageContent=type("ImageContent", (), {})))
    _client_stub = types.ModuleType("mcp.client")
    _streamable_stub = types.ModuleType("mcp.client.streamable_http")
    _sse_stub = types.ModuleType("mcp.client.sse")

    class _StubContext:
        async def __aenter__(self) -> tuple[None, None, None]:
            return (None, None, None)

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
            return False

    def _streamablehttp_client(**kwargs: object) -> _StubContext:
        _ = kwargs
        return _StubContext()

    def _sse_client(**kwargs: object) -> _StubContext:
        _ = kwargs
        return _StubContext()

    setattr(_streamable_stub, "streamablehttp_client", _streamablehttp_client)
    setattr(_sse_stub, "sse_client", _sse_client)
    _ = sys.modules.setdefault("mcp", _mcp_stub)
    _ = sys.modules.setdefault("mcp.client", _client_stub)
    _ = sys.modules.setdefault("mcp.client.streamable_http", _streamable_stub)
    _ = sys.modules.setdefault("mcp.client.sse", _sse_stub)

_memory_service_stub = types.ModuleType("app.services.memory_service")
setattr(_memory_service_stub, "memory_service", types.SimpleNamespace())
_ = sys.modules.setdefault("app.services.memory_service", _memory_service_stub)


class _StubEmailService:
    async def send_mail(self, **_: object) -> None:
        return None


_email_service_stub = types.ModuleType("app.services.email_service")
setattr(_email_service_stub, "email_service", _StubEmailService())
_ = sys.modules.setdefault("app.services.email_service", _email_service_stub)


pytestmark = pytest.mark.anyio


def _enable_group_scenes(monkeypatch: pytest.MonkeyPatch) -> None:
    def _is_enabled(flag_name: str) -> bool:
        return flag_name == "group_scene_simulation_enabled"

    monkeypatch.setattr("app.api.group_scenes.feature_flags.is_enabled", _is_enabled)


async def _seed_project_context(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async with async_db_session() as session:
        session.add(Project(id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="群像场景项目", genre="权谋", theme="信任与背叛"))
        session.add(Project(id=OTHER_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="其他项目"))
        session.add(
            Character(
                id=CHARACTER_A_ID,
                project_id=DEFAULT_TEST_PROJECT_ID,
                name="沈策",
                role_type="protagonist",
                personality="克制谨慎，习惯用反问试探对手。",
                speech_patterns="短句、少量讽刺、避免直说真实目的。",
                motivations="守住边境军权。",
            )
        )
        session.add(
            Character(
                id=CHARACTER_B_ID,
                project_id=DEFAULT_TEST_PROJECT_ID,
                name="陆晚霜",
                role_type="supporting",
                personality="冷静敏锐，擅长以温和语气施压。",
                speech_patterns="语调平稳，常以事实逼迫对方让步。",
                motivations="查明密诏真相。",
            )
        )
        session.add(Character(id=OTHER_CHARACTER_ID, project_id=OTHER_PROJECT_ID, name="其他项目角色", role_type="supporting"))
        session.add(
            VoicePersona(
                id=VOICE_PERSONA_ID,
                project_id=DEFAULT_TEST_PROJECT_ID,
                user_id=DEFAULT_TEST_USER_ID,
                name="冷峻宫廷旁白",
                tone="压抑、克制",
                style="多潜台词，少解释",
                point_of_view="第三人称限知",
                constraints="不要作者跳出点评。",
                enabled=True,
            )
        )
        session.add(
            LorebookEntry(
                id=LORE_ID,
                project_id=DEFAULT_TEST_PROJECT_ID,
                user_id=DEFAULT_TEST_USER_ID,
                title="北境密诏",
                content="皇帝曾下密诏要求北境军不得擅离关隘，否则视为谋逆。",
                activation_keys=["密诏", "北境"],
                enabled=True,
            )
        )
        await session.commit()


async def test_two_character_scene_persists(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_group_scenes(monkeypatch)
    await _seed_project_context(async_db_session)

    response = await test_client.post(
        f"/api/group-scenes/projects/{DEFAULT_TEST_PROJECT_ID}/draft",
        json={
            "title": "密诏摊牌",
            "scenario": "沈策与陆晚霜在雨夜书房围绕密诏互相试探，必须写出潜台词。",
            "participant_character_ids": [CHARACTER_A_ID, CHARACTER_B_ID],
            "selected_voice_persona_id": VOICE_PERSONA_ID,
            "selected_lore_ids": [LORE_ID],
            "prompt_context": "参考上一章结尾：烛火熄灭前，陆晚霜发现信封火漆被换过。",
            "draft_text": "沈策：你来得比我预想中早。\n陆晚霜：若不是有人想让我迟到，我还能更早。",
            "user_id": "client-user-must-be-ignored",
        },
    )

    assert response.status_code == 200
    scene = response.json()
    assert scene["project_id"] == DEFAULT_TEST_PROJECT_ID
    assert scene["user_id"] == DEFAULT_TEST_USER_ID
    assert scene["participant_character_ids"] == [CHARACTER_A_ID, CHARACTER_B_ID]
    assert scene["selected_voice_persona_id"] == VOICE_PERSONA_ID
    assert scene["selected_lore_ids"] == [LORE_ID]
    assert "沈策：" in scene["draft_text"]
    trace = scene["prompt_trace"]
    assert trace["source_type"] == "group_scene"
    assert trace["boundary_decision"] == "writing_artifact_only"
    assert trace["participant_character_ids"] == [CHARACTER_A_ID, CHARACTER_B_ID]
    assert trace["selected_lore_ids"] == [LORE_ID]
    assert trace["selected_voice_persona_id"] == VOICE_PERSONA_ID
    assert "chat_room" not in trace
    assert "messages" not in scene

    list_response = await test_client.get(f"/api/group-scenes/projects/{DEFAULT_TEST_PROJECT_ID}")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    async with async_db_session() as session:
        count_result = await session.execute(select(func.count(GroupScene.id)))
        assert count_result.scalar_one() == 1


async def test_unknown_participant_rejected(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_group_scenes(monkeypatch)
    await _seed_project_context(async_db_session)

    response = await test_client.post(
        f"/api/group-scenes/projects/{DEFAULT_TEST_PROJECT_ID}/draft",
        json={
            "title": "越界角色测试",
            "scenario": "试图把其他项目角色加入当前场景。",
            "participant_character_ids": [CHARACTER_A_ID, OTHER_CHARACTER_ID],
        },
    )

    assert response.status_code in {400, 403, 404}
    assert "参与角色" in response.json()["detail"]
    async with async_db_session() as session:
        count_result = await session.execute(select(func.count(GroupScene.id)))
        assert count_result.scalar_one() == 0
