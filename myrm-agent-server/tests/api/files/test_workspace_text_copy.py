"""Workspace text editor API, copy side: POST /browse/text/copy — an exclusive numbered sibling ("name (1).ext") that
inherits line endings and BOM, never overwrites, and is guarded like the other workspace endpoints.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.api.files import workspace_text
from tests.support.workspace_text_api import BOM, copy_text, make_workspace, reasons, text_api_client


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
# POST /browse/text/copy
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_copy_writes_a_numbered_sibling_and_leaves_the_original_alone(client: AsyncClient, ws: Path):
    resp = await copy_text(client, ws, "notes.txt", "my version\n")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "notes (1).txt"
    assert (ws / "notes (1).txt").read_bytes() == b"my version\n"
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"

    second = await copy_text(client, ws, "notes.txt", "another\n")
    assert second.json()["data"]["name"] == "notes (2).txt"


@pytest.mark.anyio
async def test_copy_takes_line_endings_and_bom_from_the_original(client: AsyncClient, ws: Path):
    await copy_text(client, ws, "windows.txt", "a\nb\n")
    await copy_text(client, ws, "bom.txt", "a\nb\n")

    assert (ws / "windows (1).txt").read_bytes() == b"a\r\nb\r\n"
    assert (ws / "bom (1).txt").read_bytes() == BOM + b"a\nb\n"


@pytest.mark.anyio
async def test_copy_next_to_a_read_only_original_uses_plain_lf(client: AsyncClient, ws: Path):
    resp = await copy_text(client, ws, "gbk.txt", "utf8 text\n")
    assert resp.status_code == 200
    assert (ws / "gbk (1).txt").read_bytes() == b"utf8 text\n"


@pytest.mark.anyio
async def test_copy_moves_on_when_another_writer_takes_the_name_first(
    client: AsyncClient, ws: Path, monkeypatch: pytest.MonkeyPatch
):
    (ws / "taken.txt").write_bytes(b"someone else\n")
    names = iter(["taken.txt", "free.txt"])
    monkeypatch.setattr(workspace_text, "dedup_filename", lambda _directory, _name: next(names))

    resp = await copy_text(client, ws, "notes.txt", "mine\n")

    assert resp.status_code == 200 and resp.json()["data"]["name"] == "free.txt"
    assert (ws / "taken.txt").read_bytes() == b"someone else\n"


@pytest.mark.anyio
async def test_copy_gives_up_with_a_reason_when_no_name_ever_frees_up(
    client: AsyncClient, ws: Path, monkeypatch: pytest.MonkeyPatch
):
    (ws / "taken.txt").write_bytes(b"someone else\n")
    monkeypatch.setattr(workspace_text, "dedup_filename", lambda _directory, _name: "taken.txt")

    resp = await copy_text(client, ws, "notes.txt", "mine\n")

    assert resp.status_code == 409 and reasons(resp) == {"reason": "name_unavailable"}
    assert (ws / "taken.txt").read_bytes() == b"someone else\n"


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/etc/passwd", "../../../etc/passwd", ".env", "src", "nope.txt"])
async def test_copy_is_guarded_like_the_other_workspace_endpoints(client: AsyncClient, ws: Path, path: str):
    before = sorted(os.listdir(ws))

    resp = await copy_text(client, ws, path, "x\n")

    assert resp.status_code in (400, 404)
    assert sorted(os.listdir(ws)) == before


@pytest.mark.anyio
async def test_copy_rejects_content_that_is_not_text(client: AsyncClient, ws: Path):
    before = sorted(os.listdir(ws))

    resp = await copy_text(client, ws, "notes.txt", "a\x00b")

    assert resp.status_code == 400 and reasons(resp) == {"reason": "invalid_content"}
    assert sorted(os.listdir(ws)) == before
