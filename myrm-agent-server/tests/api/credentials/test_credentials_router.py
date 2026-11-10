"""Credential files: the router lists what is stored under `.credentials/` and deletes single files."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.credentials.router import router
from app.api.dependencies import get_workspace_root

EXPIRED_GOOGLE_TOKEN = '{"expiry": "2000-01-01T00:00:00Z"}'


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(router, prefix="/credentials")
    app.dependency_overrides[get_workspace_root] = lambda: tmp_path
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def store(workspace: Path, relative: str, content: str) -> Path:
    path = workspace / ".credentials" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


async def listed_names(client: AsyncClient) -> set[str]:
    return {item["filename"] for item in (await client.get("/credentials")).json()["files"]}


@pytest.mark.asyncio
async def test_nothing_is_listed_before_a_file_is_stored(client: AsyncClient) -> None:
    response = await client.get("/credentials")

    assert response.status_code == 200
    assert response.json() == {"files": []}


@pytest.mark.asyncio
async def test_files_are_listed_with_relative_name_size_and_expiry(client: AsyncClient, tmp_path: Path) -> None:
    store(tmp_path, "google_token.json", EXPIRED_GOOGLE_TOKEN)
    store(tmp_path, "aws/credentials", "key=1")

    files = {item["filename"]: item for item in (await client.get("/credentials")).json()["files"]}

    assert set(files) == {"google_token.json", "aws/credentials"}
    assert files["google_token.json"]["size"] == len(EXPIRED_GOOGLE_TOKEN)
    assert files["google_token.json"]["expiry_status"] == "expired"
    assert files["aws/credentials"]["size"] == len("key=1")
    assert files["aws/credentials"]["expiry_status"] is None


@pytest.mark.asyncio
async def test_a_file_is_deleted_and_its_neighbours_are_kept(client: AsyncClient, tmp_path: Path) -> None:
    gone = store(tmp_path, "google_token.json", EXPIRED_GOOGLE_TOKEN)
    store(tmp_path, "aws/credentials", "key=1")

    response = await client.delete("/credentials/google_token.json")

    assert response.status_code == 204
    assert not gone.exists()
    assert await listed_names(client) == {"aws/credentials"}


@pytest.mark.asyncio
async def test_a_nested_file_is_deleted_by_its_relative_path(client: AsyncClient, tmp_path: Path) -> None:
    store(tmp_path, "aws/credentials", "key=1")

    response = await client.delete("/credentials/aws/credentials")

    assert response.status_code == 204
    assert await listed_names(client) == set()


@pytest.mark.asyncio
async def test_deleting_a_missing_file_is_not_found(client: AsyncClient) -> None:
    response = await client.delete("/credentials/absent.json")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_path_that_climbs_out_of_the_store_is_refused(client: AsyncClient, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("keep", encoding="utf-8")

    response = await client.delete("/credentials/..%2Fsecret.txt")

    assert response.status_code == 400
    assert outside.read_text(encoding="utf-8") == "keep"


@pytest.mark.asyncio
async def test_an_absolute_path_is_refused(client: AsyncClient, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("keep", encoding="utf-8")

    response = await client.delete(f"/credentials/{outside}")

    assert response.status_code == 400
    assert outside.read_text(encoding="utf-8") == "keep"
