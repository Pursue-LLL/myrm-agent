"""Workspace text editor API, read side: GET /browse/text — content, version, editable / read-only verdict, and the
same boundary, traversal, symlink and sensitive-file guards as the other workspace endpoints.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.support.workspace_text_api import BASE, make_workspace, read_text, reasons, sha, text_api_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with text_api_client() as c:
        yield c


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return make_workspace(tmp_path)


# --------------------------------------------------------------------------------------
# GET /browse/text
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_returns_lf_text_and_the_version_of_the_raw_bytes(client: AsyncClient, ws: Path):
    resp = await read_text(client, ws, "windows.txt")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["content"] == "alpha\nbeta\n"
    assert data["version"] == sha(b"alpha\r\nbeta\r\n")
    assert (data["editable"], data["readonly_reason"], data["truncated"]) == (True, None, False)
    assert data["size"] == 13
    assert data["name"] == "windows.txt"


@pytest.mark.anyio
async def test_read_accepts_an_absolute_path_inside_the_workspace(client: AsyncClient, ws: Path):
    resp = await read_text(client, ws, str(ws / "notes.txt"))
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "alpha\nbeta\n"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "reason"),
    [("data.bin", "binary"), ("gbk.txt", "not_utf8"), ("mixed.txt", "mixed_line_endings"), ("big.txt", "too_large")],
)
async def test_read_marks_files_the_editor_cannot_round_trip_as_read_only(client: AsyncClient, ws: Path, name: str, reason: str):
    resp = await read_text(client, ws, name)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert (data["editable"], data["readonly_reason"]) == (False, reason)
    assert data["truncated"] is (reason == "too_large")


@pytest.mark.anyio
async def test_read_of_a_missing_file_is_404_with_a_reason(client: AsyncClient, ws: Path):
    resp = await read_text(client, ws, "nope.txt")
    assert resp.status_code == 404
    assert reasons(resp) == {"reason": "not_found"}


@pytest.mark.anyio
async def test_read_of_a_directory_is_rejected(client: AsyncClient, ws: Path):
    resp = await read_text(client, ws, "src")
    assert resp.status_code == 400
    assert reasons(resp) == {"reason": "not_a_file"}


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/etc/passwd", "../../../etc/passwd", ".env"])
async def test_read_is_guarded_like_the_other_workspace_endpoints(client: AsyncClient, ws: Path, path: str):
    resp = await read_text(client, ws, path)
    assert resp.status_code == 400
    assert "content" not in str(resp.json())


@pytest.mark.anyio
async def test_read_rejects_a_dangerous_workspace(client: AsyncClient):
    resp = await client.get(BASE, params={"workspace": "/etc", "path": "passwd"})
    assert resp.status_code == 400


@pytest.mark.anyio
@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
async def test_read_does_not_follow_a_symlink_out_of_the_workspace(client: AsyncClient, ws: Path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("top secret\n")
    (ws / "link.txt").symlink_to(outside)

    resp = await read_text(client, ws, "link.txt")

    assert resp.status_code == 400
    assert "top secret" not in resp.text
