from __future__ import annotations

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

from app.models import CreativeSession, CreativeSessionMessage, Project
from app.security import create_session_token

from .test_creative_sessions import OTHER_PROJECT_ID, OTHER_USER_ID, PROJECT_ID, USER_ID, api_client


def _seed_search_fixture(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Project(id=PROJECT_ID, user_id=USER_ID, title="检索项目"))
        session.add(Project(id=OTHER_PROJECT_ID, user_id=OTHER_USER_ID, title="隔离项目"))
        owner_session = CreativeSession(id="session-owner-search", project_id=PROJECT_ID, user_id=USER_ID, title="Owner Search")
        other_session = CreativeSession(id="session-other-search", project_id=OTHER_PROJECT_ID, user_id=OTHER_USER_ID, title="Other Search")
        session.add_all([owner_session, other_session])
        session.add_all(
            [
                CreativeSessionMessage(
                    id="message-owner-match",
                    session_id=owner_session.id,
                    project_id=PROJECT_ID,
                    user_id=USER_ID,
                    role="user",
                    content="The silver lantern reveals the hidden bridge.",
                    position=0,
                ),
                CreativeSessionMessage(
                    id="message-owner-other",
                    session_id=owner_session.id,
                    project_id=PROJECT_ID,
                    user_id=USER_ID,
                    role="assistant",
                    content="No matching phrase here.",
                    position=1,
                ),
                CreativeSessionMessage(
                    id="message-other-match",
                    session_id=other_session.id,
                    project_id=OTHER_PROJECT_ID,
                    user_id=OTHER_USER_ID,
                    role="user",
                    content="The silver lantern belongs to another user.",
                    position=0,
                ),
            ]
        )
        session.commit()


def test_transcript_search_is_project_and_user_scoped(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_search_fixture(session_factory)

    response = client.get(f"/api/creative-sessions/projects/{PROJECT_ID}/search", params={"query": "silver lantern"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["message_id"] for item in payload["items"]] == ["message-owner-match"]
    assert payload["items"][0]["session_title"] == "Owner Search"


def test_transcript_search_does_not_leak_to_other_user(api_client: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, session_factory = api_client
    _seed_search_fixture(session_factory)

    client.cookies.set("session_token", create_session_token(OTHER_USER_ID, 3600))
    response = client.get(f"/api/creative-sessions/projects/{PROJECT_ID}/search", params={"query": "silver lantern"})
    assert response.status_code == 404
