"""WebDAV listing: an unreadable remote is never reported as an empty folder.

[INPUT]
app.services.memory.backup.remote_sync.storage::WebDAVBackupStrategy/WebDAVBackupConfig/RemoteStorageError

[OUTPUT]
That a listing which the server refuses or cannot answer raises, while a folder that does not exist yet lists as empty.

[POS]
The real WebDAV client over an in-process ``httpx`` transport; nothing else is replaced. The S3 counterpart lives in
``test_remote_s3_client.py``.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.services.memory.backup.remote_sync.storage import RemoteStorageError, WebDAVBackupConfig, WebDAVBackupStrategy

_NAME = "myrm.20250101120000.laptop.1a2b3c4d.linux.json.gz"
_MULTISTATUS = f"""<?xml version="1.0" encoding="UTF-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/myrm-backups/</d:href>
    <d:propstat><d:prop><d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified><d:getcontentlength>0</d:getcontentlength></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/myrm-backups/{_NAME}</d:href>
    <d:propstat><d:prop><d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified><d:getcontentlength>4096</d:getcontentlength></d:prop></d:propstat>
  </d:response>
</d:multistatus>"""


def _serve(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    real_client = httpx.AsyncClient

    def client(**options: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler), **options)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client)


def _strategy() -> WebDAVBackupStrategy:
    return WebDAVBackupStrategy(
        WebDAVBackupConfig(host="https://dav.example.test", username="u", password="p", path="/myrm-backups")
    )


async def test_a_listing_reads_the_backups_in_the_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, lambda request: httpx.Response(207, text=_MULTISTATUS))

    files = await _strategy().list_files()

    assert [(f.file_name, f.size_bytes) for f in files] == [(_NAME, 4096)]


async def test_a_folder_that_does_not_exist_yet_lists_as_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # The first upload creates it; reading a fresh setup must not look like an error.
    _serve(monkeypatch, lambda request: httpx.Response(404))

    assert await _strategy().list_files() == []


@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
async def test_a_refused_listing_raises_instead_of_looking_like_an_empty_folder(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _serve(monkeypatch, lambda request: httpx.Response(status_code))

    with pytest.raises(RemoteStorageError, match=str(status_code)):
        await _strategy().list_files()


async def test_an_unreachable_server_raises_instead_of_looking_like_an_empty_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    _serve(monkeypatch, refuse)

    with pytest.raises(httpx.ConnectError):
        await _strategy().list_files()
