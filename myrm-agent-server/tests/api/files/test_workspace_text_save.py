"""Workspace text editor API, save side: PUT /browse/text — compare-and-swap against ``base_version`` (409 with the
current version on conflict), byte-exact line endings and BOM, guards, and no route that writes without a version
check.
"""

import asyncio
import base64
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.api.files import workspace_text
from app.services.files.text_edit_io import EDITABLE_MAX_BYTES
from tests.support.workspace_text_api import BASE, BOM, b64, make_workspace, read_text, reasons, save_text, sha, text_api_client


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
# PUT /browse/text
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_save_replaces_the_file_and_the_returned_version_matches_a_fresh_read(client: AsyncClient, ws: Path):
    version = (await read_text(client, ws, "notes.txt")).json()["data"]["version"]

    resp = await save_text(client, ws, "notes.txt", "alpha\nGAMMA\n", version)

    assert resp.status_code == 200
    saved = resp.json()["data"]
    assert (ws / "notes.txt").read_bytes() == b"alpha\nGAMMA\n"
    assert saved["changed"] is True and saved["size"] == 12
    assert (await read_text(client, ws, "notes.txt")).json()["data"]["version"] == saved["version"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "edited", "expected"),
    [
        ("windows.txt", "alpha\nGAMMA\n", b"alpha\r\nGAMMA\r\n"),
        ("bom.txt", "alpha\nGAMMA\n", BOM + b"alpha\nGAMMA\n"),
    ],
)
async def test_save_restores_line_endings_and_bom_of_the_original(
    client: AsyncClient, ws: Path, name: str, edited: str, expected: bytes
):
    version = (await read_text(client, ws, name)).json()["data"]["version"]
    resp = await save_text(client, ws, name, edited, version)
    assert resp.status_code == 200
    assert (ws / name).read_bytes() == expected


@pytest.mark.anyio
async def test_saving_unchanged_text_reports_no_change_and_keeps_the_version(client: AsyncClient, ws: Path):
    version = (await read_text(client, ws, "windows.txt")).json()["data"]["version"]

    resp = await save_text(client, ws, "windows.txt", "alpha\nbeta\n", version)

    data = resp.json()["data"]
    assert resp.status_code == 200 and data["changed"] is False and data["version"] == version


@pytest.mark.anyio
async def test_a_stale_save_is_a_409_that_carries_the_current_version_and_leaves_the_file_alone(client: AsyncClient, ws: Path):
    stale = (await read_text(client, ws, "notes.txt")).json()["data"]["version"]
    (ws / "notes.txt").write_bytes(b"the agent was here\n")

    resp = await save_text(client, ws, "notes.txt", "my edit\n", stale)

    assert resp.status_code == 409
    assert reasons(resp) == {"reason": "version_conflict", "current_version": sha(b"the agent was here\n")}
    assert (ws / "notes.txt").read_bytes() == b"the agent was here\n"


@pytest.mark.anyio
async def test_overwriting_after_a_conflict_is_a_fresh_read_followed_by_a_save(client: AsyncClient, ws: Path):
    stale = (await read_text(client, ws, "notes.txt")).json()["data"]["version"]
    (ws / "notes.txt").write_bytes(b"the agent was here\n")
    assert (await save_text(client, ws, "notes.txt", "my edit\n", stale)).status_code == 409

    current = (await read_text(client, ws, "notes.txt")).json()["data"]["version"]
    resp = await save_text(client, ws, "notes.txt", "my edit\n", current)

    assert resp.status_code == 200
    assert (ws / "notes.txt").read_bytes() == b"my edit\n"


@pytest.mark.anyio
async def test_two_saves_racing_from_one_version_have_exactly_one_winner(client: AsyncClient, ws: Path):
    version = (await read_text(client, ws, "notes.txt")).json()["data"]["version"]

    first, second = await asyncio.gather(
        save_text(client, ws, "notes.txt", "writer one\n", version),
        save_text(client, ws, "notes.txt", "writer two\n", version),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    winner = "writer one\n" if first.status_code == 200 else "writer two\n"
    assert (ws / "notes.txt").read_text() == winner


@pytest.mark.anyio
async def test_a_base_version_is_mandatory_and_must_be_a_sha256(client: AsyncClient, ws: Path):
    without = await client.put(BASE, json={"workspace": str(ws), "path": "notes.txt", "content_b64": b64("x")})
    malformed = await save_text(client, ws, "notes.txt", "x", "not-a-version")

    assert without.status_code == 422 and malformed.status_code == 422
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["data.bin", "gbk.txt", "mixed.txt"])
async def test_a_file_that_cannot_round_trip_is_refused_with_its_reason(client: AsyncClient, ws: Path, name: str):
    raw = (ws / name).read_bytes()

    resp = await save_text(client, ws, name, "replacement\n", sha(raw))

    assert resp.status_code == 400
    assert reasons(resp)["reason"] in {"binary", "not_utf8", "mixed_line_endings"}
    assert (ws / name).read_bytes() == raw


@pytest.mark.anyio
async def test_an_oversized_file_is_refused_as_too_large(client: AsyncClient, ws: Path):
    resp = await save_text(client, ws, "big.txt", "x", "0" * 64)
    assert resp.status_code == 400 and reasons(resp) == {"reason": "too_large"}


@pytest.mark.anyio
async def test_saving_a_missing_file_is_404_and_creates_nothing(client: AsyncClient, ws: Path):
    resp = await save_text(client, ws, "brand_new.txt", "x", "0" * 64)
    assert resp.status_code == 404 and reasons(resp) == {"reason": "not_found"}
    assert not (ws / "brand_new.txt").exists()


@pytest.mark.anyio
async def test_saving_over_a_directory_is_rejected(client: AsyncClient, ws: Path):
    resp = await save_text(client, ws, "src", "x", "0" * 64)
    assert resp.status_code == 400 and reasons(resp) == {"reason": "not_a_file"}


@pytest.mark.anyio
async def test_content_that_is_not_base64_utf8_is_rejected(client: AsyncClient, ws: Path):
    version = sha(b"alpha\nbeta\n")
    not_base64 = await client.put(
        BASE, json={"workspace": str(ws), "path": "notes.txt", "content_b64": "***", "base_version": version}
    )
    not_utf8 = await client.put(
        BASE,
        json={
            "workspace": str(ws),
            "path": "notes.txt",
            "content_b64": base64.b64encode(b"\xff\xfe").decode(),
            "base_version": version,
        },
    )

    assert not_base64.status_code == 400 and reasons(not_base64) == {"reason": "invalid_content"}
    assert not_utf8.status_code == 400 and reasons(not_utf8) == {"reason": "invalid_content"}
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"


@pytest.mark.anyio
async def test_text_that_would_make_the_file_uneditable_is_rejected(client: AsyncClient, ws: Path):
    version = sha(b"alpha\nbeta\n")

    with_nul = await save_text(client, ws, "notes.txt", "a\x00b", version)
    too_big = await save_text(client, ws, "notes.txt", "x" * (EDITABLE_MAX_BYTES + 1), version)

    assert with_nul.status_code == 400 and reasons(with_nul) == {"reason": "invalid_content"}
    assert too_big.status_code == 400 and reasons(too_big) == {"reason": "content_too_large"}
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"


@pytest.mark.anyio
async def test_a_save_that_cannot_be_written_is_reported_as_write_blocked(
    client: AsyncClient, ws: Path, monkeypatch: pytest.MonkeyPatch
):
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise workspace_text.WriteBlocked("locked")

    monkeypatch.setattr(workspace_text, "write_text_if_version", blocked)

    resp = await save_text(client, ws, "notes.txt", "x", sha(b"alpha\nbeta\n"))

    assert resp.status_code == 400 and reasons(resp) == {"reason": "write_blocked"}


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/etc/passwd", "../../../tmp/evil.txt", ".env"])
async def test_save_is_guarded_like_the_other_workspace_endpoints(client: AsyncClient, ws: Path, path: str):
    resp = await save_text(client, ws, path, "hacked\n", "0" * 64)
    assert resp.status_code == 400
    assert (ws / ".env").read_bytes() == b"SECRET=1\n"


@pytest.mark.anyio
@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
async def test_save_does_not_follow_a_symlink_out_of_the_workspace(client: AsyncClient, ws: Path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "target.txt"
    outside.write_bytes(b"untouched\n")
    (ws / "link.txt").symlink_to(outside)

    resp = await save_text(client, ws, "link.txt", "hacked\n", sha(b"untouched\n"))

    assert resp.status_code == 400
    assert outside.read_bytes() == b"untouched\n"


@pytest.mark.anyio
async def test_editor_text_survives_request_sanitising_byte_for_byte(client: AsyncClient, ws: Path):
    """The app under test carries TextSanitizerMiddleware; base64 keeps the file's own bytes out of its reach."""
    awkward = "<|endoftext|> \x1b[31mred\x1b[0m \ufffd end\n"
    version = (await read_text(client, ws, "notes.txt")).json()["data"]["version"]

    resp = await save_text(client, ws, "notes.txt", awkward, version)

    assert resp.status_code == 200
    assert (ws / "notes.txt").read_bytes() == awkward.encode("utf-8")
    assert (await read_text(client, ws, "notes.txt")).json()["data"]["content"] == awkward


# --------------------------------------------------------------------------------------
# No unversioned write route
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_no_route_writes_a_file_without_a_version_check(client: AsyncClient, ws: Path):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={"workspace": str(ws), "path": "notes.txt", "content": "overwritten"},
    )
    assert resp.status_code in (404, 405)
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"
