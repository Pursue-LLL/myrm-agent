"""Workspace text editor API: versioned read, compare-and-swap save, save as copy.

Covers:
- GET  /browse/text      — content + version + editable / read-only verdict
- PUT  /browse/text      — save against ``base_version`` (409 on conflict, no unconditional write path)
- POST /browse/text/copy — exclusive sibling file ("name (1).ext")
- Security parity with the other workspace endpoints: boundary, traversal, symlink escape, sensitive files
- The retired ``PUT /browse/content`` stays gone
"""

import asyncio
import base64
import hashlib
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.files import workspace_text
from app.middleware.text_sanitizer_middleware import TextSanitizerMiddleware
from app.services.files.text_edit_io import EDITABLE_MAX_BYTES
from tests.support.minimal_app import build_minimal_app

BASE = "/api/v1/files/browse/text"
BOM = b"\xef\xbb\xbf"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _error_body(resp) -> dict:
    """The structured error, whether the handler wrapped it in ``detail`` or returned it at top level."""
    body = resp.json()
    return body["detail"] if "detail" in body else body


def _reasons(resp) -> dict[str, str]:
    """``{field: issue}`` from the response's error details."""
    error = _error_body(resp).get("error") or {}
    return {d["field"]: d["issue"] for d in error.get("details", [])}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app: FastAPI = build_minimal_app(preset="files")
    app.add_middleware(TextSanitizerMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    (tmp_path / "notes.txt").write_bytes(b"alpha\nbeta\n")
    (tmp_path / "windows.txt").write_bytes(b"alpha\r\nbeta\r\n")
    (tmp_path / "bom.txt").write_bytes(BOM + b"alpha\nbeta\n")
    (tmp_path / "data.bin").write_bytes(b"MZ\x00\x01")
    (tmp_path / "gbk.txt").write_bytes(b"\xd0\xd5\xc3\xfb\n")
    (tmp_path / "mixed.txt").write_bytes(b"a\r\nb\nc\r\n")
    (tmp_path / "big.txt").write_bytes(b"x" * (EDITABLE_MAX_BYTES + 100))
    (tmp_path / ".env").write_bytes(b"SECRET=1\n")
    (tmp_path / "src").mkdir()
    return tmp_path


async def _read(client: AsyncClient, ws: Path, path: str):
    return await client.get(BASE, params={"workspace": str(ws), "path": path})


async def _save(client: AsyncClient, ws: Path, path: str, text: str, base_version: str):
    return await client.put(
        BASE,
        json={"workspace": str(ws), "path": path, "content_b64": _b64(text), "base_version": base_version},
    )


async def _copy(client: AsyncClient, ws: Path, path: str, text: str):
    return await client.post(
        f"{BASE}/copy",
        json={"workspace": str(ws), "path": path, "content_b64": _b64(text)},
    )


# --------------------------------------------------------------------------------------
# GET /browse/text
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_returns_lf_text_and_the_version_of_the_raw_bytes(client: AsyncClient, ws: Path):
    resp = await _read(client, ws, "windows.txt")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["content"] == "alpha\nbeta\n"
    assert data["version"] == _sha(b"alpha\r\nbeta\r\n")
    assert (data["editable"], data["readonly_reason"], data["truncated"]) == (True, None, False)
    assert data["size"] == 13
    assert data["name"] == "windows.txt"


@pytest.mark.anyio
async def test_read_accepts_an_absolute_path_inside_the_workspace(client: AsyncClient, ws: Path):
    resp = await _read(client, ws, str(ws / "notes.txt"))
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "alpha\nbeta\n"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "reason"),
    [("data.bin", "binary"), ("gbk.txt", "not_utf8"), ("mixed.txt", "mixed_line_endings"), ("big.txt", "too_large")],
)
async def test_read_marks_files_the_editor_cannot_round_trip_as_read_only(client: AsyncClient, ws: Path, name: str, reason: str):
    resp = await _read(client, ws, name)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert (data["editable"], data["readonly_reason"]) == (False, reason)
    assert data["truncated"] is (reason == "too_large")


@pytest.mark.anyio
async def test_read_of_a_missing_file_is_404_with_a_reason(client: AsyncClient, ws: Path):
    resp = await _read(client, ws, "nope.txt")
    assert resp.status_code == 404
    assert _reasons(resp) == {"reason": "not_found"}


@pytest.mark.anyio
async def test_read_of_a_directory_is_rejected(client: AsyncClient, ws: Path):
    resp = await _read(client, ws, "src")
    assert resp.status_code == 400
    assert _reasons(resp) == {"reason": "not_a_file"}


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/etc/passwd", "../../../etc/passwd", ".env"])
async def test_read_is_guarded_like_the_other_workspace_endpoints(client: AsyncClient, ws: Path, path: str):
    resp = await _read(client, ws, path)
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

    resp = await _read(client, ws, "link.txt")

    assert resp.status_code == 400
    assert "top secret" not in resp.text


# --------------------------------------------------------------------------------------
# PUT /browse/text
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_save_replaces_the_file_and_the_returned_version_matches_a_fresh_read(client: AsyncClient, ws: Path):
    version = (await _read(client, ws, "notes.txt")).json()["data"]["version"]

    resp = await _save(client, ws, "notes.txt", "alpha\nGAMMA\n", version)

    assert resp.status_code == 200
    saved = resp.json()["data"]
    assert (ws / "notes.txt").read_bytes() == b"alpha\nGAMMA\n"
    assert saved["changed"] is True and saved["size"] == 12
    assert (await _read(client, ws, "notes.txt")).json()["data"]["version"] == saved["version"]


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
    version = (await _read(client, ws, name)).json()["data"]["version"]
    resp = await _save(client, ws, name, edited, version)
    assert resp.status_code == 200
    assert (ws / name).read_bytes() == expected


@pytest.mark.anyio
async def test_saving_unchanged_text_reports_no_change_and_keeps_the_version(client: AsyncClient, ws: Path):
    version = (await _read(client, ws, "windows.txt")).json()["data"]["version"]

    resp = await _save(client, ws, "windows.txt", "alpha\nbeta\n", version)

    data = resp.json()["data"]
    assert resp.status_code == 200 and data["changed"] is False and data["version"] == version


@pytest.mark.anyio
async def test_a_stale_save_is_a_409_that_carries_the_current_version_and_leaves_the_file_alone(client: AsyncClient, ws: Path):
    stale = (await _read(client, ws, "notes.txt")).json()["data"]["version"]
    (ws / "notes.txt").write_bytes(b"the agent was here\n")

    resp = await _save(client, ws, "notes.txt", "my edit\n", stale)

    assert resp.status_code == 409
    assert _reasons(resp) == {"reason": "version_conflict", "current_version": _sha(b"the agent was here\n")}
    assert (ws / "notes.txt").read_bytes() == b"the agent was here\n"


@pytest.mark.anyio
async def test_overwriting_after_a_conflict_is_a_fresh_read_followed_by_a_save(client: AsyncClient, ws: Path):
    stale = (await _read(client, ws, "notes.txt")).json()["data"]["version"]
    (ws / "notes.txt").write_bytes(b"the agent was here\n")
    assert (await _save(client, ws, "notes.txt", "my edit\n", stale)).status_code == 409

    current = (await _read(client, ws, "notes.txt")).json()["data"]["version"]
    resp = await _save(client, ws, "notes.txt", "my edit\n", current)

    assert resp.status_code == 200
    assert (ws / "notes.txt").read_bytes() == b"my edit\n"


@pytest.mark.anyio
async def test_two_saves_racing_from_one_version_have_exactly_one_winner(client: AsyncClient, ws: Path):
    version = (await _read(client, ws, "notes.txt")).json()["data"]["version"]

    first, second = await asyncio.gather(
        _save(client, ws, "notes.txt", "writer one\n", version),
        _save(client, ws, "notes.txt", "writer two\n", version),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    winner = "writer one\n" if first.status_code == 200 else "writer two\n"
    assert (ws / "notes.txt").read_text() == winner


@pytest.mark.anyio
async def test_a_base_version_is_mandatory_and_must_be_a_sha256(client: AsyncClient, ws: Path):
    without = await client.put(BASE, json={"workspace": str(ws), "path": "notes.txt", "content_b64": _b64("x")})
    malformed = await _save(client, ws, "notes.txt", "x", "not-a-version")

    assert without.status_code == 422 and malformed.status_code == 422
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["data.bin", "gbk.txt", "mixed.txt"])
async def test_a_file_that_cannot_round_trip_is_refused_with_its_reason(client: AsyncClient, ws: Path, name: str):
    raw = (ws / name).read_bytes()

    resp = await _save(client, ws, name, "replacement\n", _sha(raw))

    assert resp.status_code == 400
    assert _reasons(resp)["reason"] in {"binary", "not_utf8", "mixed_line_endings"}
    assert (ws / name).read_bytes() == raw


@pytest.mark.anyio
async def test_an_oversized_file_is_refused_as_too_large(client: AsyncClient, ws: Path):
    resp = await _save(client, ws, "big.txt", "x", "0" * 64)
    assert resp.status_code == 400 and _reasons(resp) == {"reason": "too_large"}


@pytest.mark.anyio
async def test_saving_a_missing_file_is_404_and_creates_nothing(client: AsyncClient, ws: Path):
    resp = await _save(client, ws, "brand_new.txt", "x", "0" * 64)
    assert resp.status_code == 404 and _reasons(resp) == {"reason": "not_found"}
    assert not (ws / "brand_new.txt").exists()


@pytest.mark.anyio
async def test_saving_over_a_directory_is_rejected(client: AsyncClient, ws: Path):
    resp = await _save(client, ws, "src", "x", "0" * 64)
    assert resp.status_code == 400 and _reasons(resp) == {"reason": "not_a_file"}


@pytest.mark.anyio
async def test_content_that_is_not_base64_utf8_is_rejected(client: AsyncClient, ws: Path):
    version = _sha(b"alpha\nbeta\n")
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

    assert not_base64.status_code == 400 and _reasons(not_base64) == {"reason": "invalid_content"}
    assert not_utf8.status_code == 400 and _reasons(not_utf8) == {"reason": "invalid_content"}
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"


@pytest.mark.anyio
async def test_text_that_would_make_the_file_uneditable_is_rejected(client: AsyncClient, ws: Path):
    version = _sha(b"alpha\nbeta\n")

    with_nul = await _save(client, ws, "notes.txt", "a\x00b", version)
    too_big = await _save(client, ws, "notes.txt", "x" * (EDITABLE_MAX_BYTES + 1), version)

    assert with_nul.status_code == 400 and _reasons(with_nul) == {"reason": "invalid_content"}
    assert too_big.status_code == 400 and _reasons(too_big) == {"reason": "content_too_large"}
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"


@pytest.mark.anyio
async def test_a_save_that_cannot_be_written_is_reported_as_write_blocked(
    client: AsyncClient, ws: Path, monkeypatch: pytest.MonkeyPatch
):
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise workspace_text.WriteBlocked("locked")

    monkeypatch.setattr(workspace_text, "write_text_if_version", blocked)

    resp = await _save(client, ws, "notes.txt", "x", _sha(b"alpha\nbeta\n"))

    assert resp.status_code == 400 and _reasons(resp) == {"reason": "write_blocked"}


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/etc/passwd", "../../../tmp/evil.txt", ".env"])
async def test_save_is_guarded_like_the_other_workspace_endpoints(client: AsyncClient, ws: Path, path: str):
    resp = await _save(client, ws, path, "hacked\n", "0" * 64)
    assert resp.status_code == 400
    assert (ws / ".env").read_bytes() == b"SECRET=1\n"


@pytest.mark.anyio
@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
async def test_save_does_not_follow_a_symlink_out_of_the_workspace(client: AsyncClient, ws: Path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "target.txt"
    outside.write_bytes(b"untouched\n")
    (ws / "link.txt").symlink_to(outside)

    resp = await _save(client, ws, "link.txt", "hacked\n", _sha(b"untouched\n"))

    assert resp.status_code == 400
    assert outside.read_bytes() == b"untouched\n"


@pytest.mark.anyio
async def test_editor_text_survives_request_sanitising_byte_for_byte(client: AsyncClient, ws: Path):
    """The app under test carries TextSanitizerMiddleware; base64 keeps the file's own bytes out of its reach."""
    awkward = "<|endoftext|> \x1b[31mred\x1b[0m \ufffd end\n"
    version = (await _read(client, ws, "notes.txt")).json()["data"]["version"]

    resp = await _save(client, ws, "notes.txt", awkward, version)

    assert resp.status_code == 200
    assert (ws / "notes.txt").read_bytes() == awkward.encode("utf-8")
    assert (await _read(client, ws, "notes.txt")).json()["data"]["content"] == awkward


# --------------------------------------------------------------------------------------
# POST /browse/text/copy
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_copy_writes_a_numbered_sibling_and_leaves_the_original_alone(client: AsyncClient, ws: Path):
    resp = await _copy(client, ws, "notes.txt", "my version\n")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "notes (1).txt"
    assert (ws / "notes (1).txt").read_bytes() == b"my version\n"
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"

    second = await _copy(client, ws, "notes.txt", "another\n")
    assert second.json()["data"]["name"] == "notes (2).txt"


@pytest.mark.anyio
async def test_copy_takes_line_endings_and_bom_from_the_original(client: AsyncClient, ws: Path):
    await _copy(client, ws, "windows.txt", "a\nb\n")
    await _copy(client, ws, "bom.txt", "a\nb\n")

    assert (ws / "windows (1).txt").read_bytes() == b"a\r\nb\r\n"
    assert (ws / "bom (1).txt").read_bytes() == BOM + b"a\nb\n"


@pytest.mark.anyio
async def test_copy_next_to_a_read_only_original_uses_plain_lf(client: AsyncClient, ws: Path):
    resp = await _copy(client, ws, "gbk.txt", "utf8 text\n")
    assert resp.status_code == 200
    assert (ws / "gbk (1).txt").read_bytes() == b"utf8 text\n"


@pytest.mark.anyio
async def test_copy_moves_on_when_another_writer_takes_the_name_first(
    client: AsyncClient, ws: Path, monkeypatch: pytest.MonkeyPatch
):
    (ws / "taken.txt").write_bytes(b"someone else\n")
    names = iter(["taken.txt", "free.txt"])
    monkeypatch.setattr(workspace_text, "dedup_filename", lambda _directory, _name: next(names))

    resp = await _copy(client, ws, "notes.txt", "mine\n")

    assert resp.status_code == 200 and resp.json()["data"]["name"] == "free.txt"
    assert (ws / "taken.txt").read_bytes() == b"someone else\n"


@pytest.mark.anyio
async def test_copy_gives_up_with_a_reason_when_no_name_ever_frees_up(
    client: AsyncClient, ws: Path, monkeypatch: pytest.MonkeyPatch
):
    (ws / "taken.txt").write_bytes(b"someone else\n")
    monkeypatch.setattr(workspace_text, "dedup_filename", lambda _directory, _name: "taken.txt")

    resp = await _copy(client, ws, "notes.txt", "mine\n")

    assert resp.status_code == 409 and _reasons(resp) == {"reason": "name_unavailable"}
    assert (ws / "taken.txt").read_bytes() == b"someone else\n"


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/etc/passwd", "../../../etc/passwd", ".env", "src", "nope.txt"])
async def test_copy_is_guarded_like_the_other_workspace_endpoints(client: AsyncClient, ws: Path, path: str):
    before = sorted(os.listdir(ws))

    resp = await _copy(client, ws, path, "x\n")

    assert resp.status_code in (400, 404)
    assert sorted(os.listdir(ws)) == before


@pytest.mark.anyio
async def test_copy_rejects_content_that_is_not_text(client: AsyncClient, ws: Path):
    before = sorted(os.listdir(ws))

    resp = await _copy(client, ws, "notes.txt", "a\x00b")

    assert resp.status_code == 400 and _reasons(resp) == {"reason": "invalid_content"}
    assert sorted(os.listdir(ws)) == before


# --------------------------------------------------------------------------------------
# Retired endpoint
# --------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_old_unconditional_save_endpoint_is_gone(client: AsyncClient, ws: Path):
    resp = await client.put(
        "/api/v1/files/browse/content",
        json={"workspace": str(ws), "path": "notes.txt", "content": "overwritten"},
    )
    assert resp.status_code in (404, 405)
    assert (ws / "notes.txt").read_bytes() == b"alpha\nbeta\n"
