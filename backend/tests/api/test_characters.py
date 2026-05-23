from __future__ import annotations

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from collections.abc import AsyncIterator, Iterator
import json
from typing import cast

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.middleware import auth_middleware
from app.models import Project
from app.security import create_session_token

from .test_creative_sessions import AsyncSessionAdapter, SyncSessionProtocol, USER_ID, app


PROJECT_ID = "project-character-card-api"


class CharacterSessionAdapter(AsyncSessionAdapter):
    async def flush(self) -> None:
        cast(SyncSessionProtocol, self.session).flush()


@pytest.fixture()
def character_api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

    async def fake_get_user(user_id: str) -> object:
        return type("User", (), {"id": user_id, "user_id": user_id, "username": user_id, "trust_level": 1, "is_admin": False})()

    async def override_get_db() -> AsyncIterator[CharacterSessionAdapter]:
        with session_factory() as session:
            yield CharacterSessionAdapter(session)

    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            client.cookies.set("session_token", create_session_token(USER_ID, 3600))
            yield client, session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _seed_project(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="角色卡项目"))
        session.commit()


def test_character_card_fields_persist_and_export(character_api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = character_api_client
    _seed_project(session_factory)

    create_response = client.post(
        "/api/characters",
        json={
            "project_id": PROJECT_ID,
            "name": "阿岚",
            "role_type": "supporting",
            "personality": "外冷内热",
            "writing_notes": "她在第三卷前不能暴露真实身份。",
            "speech_patterns": "常用反问，句尾省略。",
            "motivations": "守住边城并寻找妹妹。",
            "arc_summary": "从逃避责任到主动继承守城职责。",
            "card_version": 1,
            "user_id": "client-supplied-user-must-be-ignored",
        },
    )
    assert create_response.status_code == 200
    character = create_response.json()
    assert character["writing_notes"] == "她在第三卷前不能暴露真实身份。"
    assert character["speech_patterns"] == "常用反问，句尾省略。"
    assert character["motivations"] == "守住边城并寻找妹妹。"
    assert character["arc_summary"] == "从逃避责任到主动继承守城职责。"
    assert character["card_version"] == 1

    export_response = client.post("/api/characters/export", json={"character_ids": [character["id"]]})
    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["version"] == "1.2.0"
    exported_card = exported["data"][0]
    assert exported_card["writing_notes"] == "她在第三卷前不能暴露真实身份。"
    assert exported_card["speech_patterns"] == "常用反问，句尾省略。"
    assert exported_card["motivations"] == "守住边城并寻找妹妹。"
    assert exported_card["arc_summary"] == "从逃避责任到主动继承守城职责。"
    assert exported_card["card_version"] == 1


def test_invalid_character_card_payload_rejected(character_api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = character_api_client
    _seed_project(session_factory)

    response = client.post(
        "/api/characters",
        json={
            "project_id": PROJECT_ID,
            "name": "阿岚",
            "role_type": "supporting",
            "writing_notes": "有效文本",
            "card_version": 0,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "请求参数验证失败"


def test_character_import_validation_rejects_malformed_card_fields(character_api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = character_api_client
    _seed_project(session_factory)
    malformed = {
        "version": "1.2.0",
        "export_type": "characters",
        "data": [{"name": "破损角色", "writing_notes": ["bad"], "card_version": False}],
    }

    response = client.post(
        "/api/characters/validate-import",
        files={"file": ("characters.json", json.dumps(malformed), "application/json")},
    )

    assert response.status_code == 200
    validation = response.json()
    assert validation["valid"] is False
    assert "第1个角色的writing_notes字段必须是字符串" in validation["errors"]
    assert "第1个角色的card_version字段必须是大于等于1的整数" in validation["errors"]
