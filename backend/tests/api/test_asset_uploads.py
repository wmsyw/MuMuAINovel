from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false

import base64
from pathlib import Path
import sys
import types

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Project, ProjectAsset


DEFAULT_TEST_PROJECT_ID = "project-test-default"
DEFAULT_TEST_USER_ID = "user-test-default"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


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


async def _seed_asset_projects(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async with async_db_session() as session:
        session.add(Project(id=DEFAULT_TEST_PROJECT_ID, user_id=DEFAULT_TEST_USER_ID, title="本地资源项目"))
        session.add(Project(id="project-other-user", user_id="other-user", title="他人项目"))
        await session.commit()


def _use_tmp_asset_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from app.services import project_asset_service as service_module

    asset_root = tmp_path / "project-assets"
    monkeypatch.setattr(service_module, "LOCAL_ASSET_STORAGE_ROOT", asset_root)
    return asset_root


def _enable_local_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.project_assets.feature_flags.is_enabled", lambda flag_name: flag_name == "local_assets_enabled")


async def test_local_assets_disabled_by_default(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_tmp_asset_root(monkeypatch, tmp_path)
    await _seed_asset_projects(async_db_session)

    response = await test_client.get(f"/api/projects/{DEFAULT_TEST_PROJECT_ID}/assets")
    assert response.status_code == 404
    assert response.json() == {"detail": "本地资源功能未启用"}

    openapi_response = await test_client.get("/openapi.json")
    assert openapi_response.status_code == 200
    assert "/api/projects/{project_id}/assets" not in openapi_response.json()["paths"]

    upload_response = await test_client.post(
        f"/api/projects/{DEFAULT_TEST_PROJECT_ID}/assets",
        data={"asset_type": "avatar", "display_name": "主角头像"},
        files={"file": ("hero.png", PNG_BYTES, "image/png")},
    )
    assert upload_response.status_code == 404


async def test_local_upload_round_trip(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_local_assets(monkeypatch)
    asset_root = _use_tmp_asset_root(monkeypatch, tmp_path)
    await _seed_asset_projects(async_db_session)

    upload_response = await test_client.post(
        f"/api/projects/{DEFAULT_TEST_PROJECT_ID}/assets",
        data={"asset_type": "avatar", "display_name": "主角头像"},
        files={"file": ("hero.png", PNG_BYTES, "image/png")},
    )
    assert upload_response.status_code == 200
    asset = upload_response.json()
    assert asset["project_id"] == DEFAULT_TEST_PROJECT_ID
    assert asset["user_id"] == DEFAULT_TEST_USER_ID
    assert asset["asset_type"] == "avatar"
    assert asset["display_name"] == "主角头像"
    assert asset["original_filename"] == "hero.png"
    assert asset["storage_filename"] != "hero.png"
    assert asset["mime_type"] == "image/png"
    assert asset["file_size"] == len(PNG_BYTES)
    assert asset["file_url"] == f"/api/projects/{DEFAULT_TEST_PROJECT_ID}/assets/{asset['id']}/file"
    stored_files = [path for path in asset_root.rglob("*") if path.is_file()]
    assert len(stored_files) == 1
    assert stored_files[0].resolve().relative_to(asset_root.resolve())

    list_response = await test_client.get(f"/api/projects/{DEFAULT_TEST_PROJECT_ID}/assets", params={"asset_type": "avatar"})
    assert list_response.status_code == 200
    listing = list_response.json()
    assert listing["total"] == 1
    assert [item["id"] for item in listing["items"]] == [asset["id"]]

    file_response = await test_client.get(asset["file_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("image/png")
    assert file_response.content == PNG_BYTES

    denied_response = await test_client.get("/api/projects/project-other-user/assets")
    assert denied_response.status_code == 404

    delete_response = await test_client.delete(f"/api/projects/{DEFAULT_TEST_PROJECT_ID}/assets/{asset['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert not any(path.is_file() for path in asset_root.rglob("*"))


async def test_path_traversal_filename_rejected(
    test_client: AsyncClient,
    async_db_session: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_local_assets(monkeypatch)
    asset_root = _use_tmp_asset_root(monkeypatch, tmp_path)
    await _seed_asset_projects(async_db_session)

    response = await test_client.post(
        f"/api/projects/{DEFAULT_TEST_PROJECT_ID}/assets",
        data={"asset_type": "avatar", "display_name": "越界文件"},
        files={"file": ("../../evil.txt", b"not an image", "text/plain")},
    )
    assert response.status_code in {400, 422}
    assert "路径" in response.json()["detail"]
    assert not any(path.is_file() for path in asset_root.rglob("*"))

    async with async_db_session() as session:
        count_result = await session.execute(select(func.count(ProjectAsset.id)))
        assert count_result.scalar_one() == 0
