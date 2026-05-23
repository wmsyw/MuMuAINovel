from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUntypedFunctionDecorator=false, reportPrivateLocalImportUsage=false

import asyncio
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.middleware import auth_middleware
from app.models import Project, User
from app.security import create_session_token


DEFAULT_TEST_USER_ID = "user-test-default"
DEFAULT_TEST_PROJECT_ID = "project-test-default"
DEFAULT_TEST_USERNAME = "测试作者"
DEFAULT_TEST_DISPLAY_NAME = "测试作者"
DEFAULT_TEST_PROJECT_TITLE = "测试项目"


def create_test_user(
    *,
    user_id: str = DEFAULT_TEST_USER_ID,
    username: str = DEFAULT_TEST_USERNAME,
    display_name: str = DEFAULT_TEST_DISPLAY_NAME,
    trust_level: int = 1,
    is_admin: bool = False,
    linuxdo_id: str | None = None,
    avatar_url: str | None = None,
) -> User:
    return User(
        user_id=user_id,
        username=username,
        display_name=display_name,
        trust_level=trust_level,
        is_admin=is_admin,
        linuxdo_id=linuxdo_id or user_id,
        avatar_url=avatar_url,
    )


def create_test_project(
    *,
    project_id: str = DEFAULT_TEST_PROJECT_ID,
    user_id: str = DEFAULT_TEST_USER_ID,
    title: str = DEFAULT_TEST_PROJECT_TITLE,
    description: str | None = None,
    theme: str | None = None,
    genre: str | None = None,
) -> Project:
    return Project(
        id=project_id,
        user_id=user_id,
        title=title,
        description=description,
        theme=theme,
        genre=genre,
    )


@pytest.fixture()
def auto_cleanup() -> Iterator[None]:
    """Restore dependency overrides after each test."""

    from app.main import app

    previous_overrides = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture()
def async_db_session() -> Iterator[async_sessionmaker[AsyncSession]]:
    """Fresh in-memory SQLite async engine/session factory for isolated tests."""

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    async def _create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture()
def test_client(
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[httpx.AsyncClient]:
    """Async HTTP client with a test DB override and default authenticated user."""

    from app.main import app

    previous_overrides = dict(app.dependency_overrides)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with async_db_session() as session:
            yield session

    async def fake_get_user(user_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            user_id=user_id,
            id=user_id,
            username=DEFAULT_TEST_USERNAME,
            display_name=DEFAULT_TEST_DISPLAY_NAME,
            trust_level=1,
            is_admin=False,
        )

    monkeypatch.setattr(auth_middleware.user_manager, "get_user", fake_get_user)
    app.dependency_overrides[get_db] = override_get_db

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    client.cookies.set("session_token", create_session_token(DEFAULT_TEST_USER_ID, 3600))

    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        asyncio.run(client.aclose())
