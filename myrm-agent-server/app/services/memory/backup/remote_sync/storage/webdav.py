"""WebDAV backup storage (Jianguoyun, Nextcloud, ownCloud or any WebDAV server) over an async ``httpx`` client.

[INPUT]
httpx::AsyncClient (POS: external HTTP client, imported on first use)
app.services.memory.backup.remote_sync.storage.base::RemoteBackupStrategy/RemoteBackupFile/RemoteStorageError (POS: provider contract)

[OUTPUT]
WebDAVBackupConfig / WebDAVBackupStrategy: the WebDAV implementation of the storage contract

[POS]
A missing backup folder (HTTP 404) lists as empty because the first upload creates it; any other listing refusal raises
``RemoteStorageError``. Listed names are percent-decoded and only direct ``.gz`` children count.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote

from app.services.memory.backup.remote_sync.storage.base import (
    RemoteBackupFile,
    RemoteBackupStrategy,
    RemoteStorageError,
)

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

_HREF_PATTERN = re.compile(r"<[^>]*href[^>]*>([^<]+)</", re.IGNORECASE)
_LASTMOD_PATTERN = re.compile(r"<[^>]*getlastmodified[^>]*>([^<]+)</", re.IGNORECASE)
_LENGTH_PATTERN = re.compile(r"<[^>]*getcontentlength[^>]*>([^<]+)</", re.IGNORECASE)
_RESPONSE_SPLIT = re.compile(r"<[^>]*response[^>]*>", re.IGNORECASE)


@dataclass
class WebDAVBackupConfig:
    """WebDAV connection settings."""

    host: str = ""
    username: str = ""
    password: str = ""
    path: str = "/myrm-backups"


class WebDAVBackupStrategy(RemoteBackupStrategy):
    """WebDAV-based remote backup strategy.

    Supports: 坚果云, Nextcloud, ownCloud, or any WebDAV server.
    """

    def __init__(self, config: WebDAVBackupConfig) -> None:
        self._config = config
        self._client: "_WebDAVClient | None" = None

    def _get_client(self) -> "_WebDAVClient":
        if self._client is None:
            self._client = _WebDAVClient(
                host=self._config.host,
                username=self._config.username,
                password=self._config.password,
                base_path=self._config.path,
            )
        return self._client

    async def upload(self, local_path: Path, remote_name: str) -> bool:
        client = self._get_client()
        return await client.put_file(local_path, remote_name)

    async def download(self, remote_name: str, local_path: Path) -> bool:
        client = self._get_client()
        return await client.get_file(remote_name, local_path)

    async def list_files(self) -> list[RemoteBackupFile]:
        client = self._get_client()
        return await client.list_files()

    async def delete(self, remote_name: str) -> bool:
        client = self._get_client()
        return await client.delete_file(remote_name)

    async def check_connection(self) -> bool:
        client = self._get_client()
        return await client.check_connection()


class _WebDAVClient:
    """Async WebDAV client using httpx for HTTP operations."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        base_path: str,
    ) -> None:
        self._host = host.rstrip("/")
        self._username = username
        self._password = password
        self._base_path = base_path.strip("/")

    def _url(self, filename: str = "") -> str:
        parts = [self._host]
        if self._base_path:
            parts.append(self._base_path)
        if filename:
            parts.append(filename)
        return "/".join(parts)

    async def _ensure_directory(self, client: "httpx.AsyncClient") -> None:
        """Ensure remote backup directory exists (MKCOL)."""
        if not self._base_path:
            return
        url = f"{self._host}/{self._base_path}/"
        resp = await client.request("MKCOL", url)
        # 201 = created, 405 = already exists, 301 = redirect (exists)
        if resp.status_code not in (201, 405, 301, 207):
            logger.debug("MKCOL %s returned %s (may already exist)", url, resp.status_code)

    async def check_connection(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=15.0,
                follow_redirects=True,
            ) as client:
                resp = await client.request("PROPFIND", self._url() + "/", headers={"Depth": "0"})
                return resp.status_code in (207, 200, 301)
        except Exception as e:
            logger.warning("WebDAV connection check failed: %s", e)
            return False

    async def put_file(self, local_path: Path, remote_name: str) -> bool:
        import httpx

        try:
            content = local_path.read_bytes()
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=300.0,
                follow_redirects=True,
            ) as client:
                await self._ensure_directory(client)
                resp = await client.put(
                    self._url(remote_name),
                    content=content,
                    headers={"Content-Type": "application/octet-stream"},
                )
                success = resp.status_code in (200, 201, 204)
                if not success:
                    logger.error("WebDAV upload failed: %s %s", resp.status_code, resp.text[:200])
                return success
        except Exception as e:
            logger.error("WebDAV upload error: %s", e)
            return False

    async def get_file(self, remote_name: str, local_path: Path) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=300.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(self._url(remote_name))
                if resp.status_code == 200:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(resp.content)
                    return True
                logger.error("WebDAV download failed: %s", resp.status_code)
                return False
        except Exception as e:
            logger.error("WebDAV download error: %s", e)
            return False

    async def list_files(self) -> list[RemoteBackupFile]:
        import httpx

        propfind_body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<propfind xmlns="DAV:">'
            "<prop><getlastmodified/><getcontentlength/></prop>"
            "</propfind>"
        )
        async with httpx.AsyncClient(
            auth=(self._username, self._password),
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            resp = await client.request(
                "PROPFIND",
                self._url() + "/",
                content=propfind_body.encode(),
                headers={"Depth": "1", "Content-Type": "application/xml"},
            )
        if resp.status_code == 404:
            return []  # nothing has been uploaded yet: the first upload creates the folder
        if resp.status_code != 207:
            raise RemoteStorageError(f"WebDAV listing refused: HTTP {resp.status_code}")
        return sorted(_parse_webdav_multistatus(resp.text), key=lambda f: f.modified_time, reverse=True)

    async def delete_file(self, remote_name: str) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                resp = await client.delete(self._url(remote_name))
                return resp.status_code in (200, 204, 404)
        except Exception as e:
            logger.error("WebDAV delete error: %s", e)
            return False


def _parse_webdav_multistatus(xml_text: str) -> list[RemoteBackupFile]:
    """Parse WebDAV PROPFIND 207 multistatus response."""
    results: list[RemoteBackupFile] = []

    for resp_block in _RESPONSE_SPLIT.split(xml_text)[1:]:
        href_match = _HREF_PATTERN.search(resp_block)
        if not href_match:
            continue
        href = href_match.group(1).strip()
        filename = unquote(href.rstrip("/").rsplit("/", 1)[-1])  # hrefs are percent-encoded
        # An encoded separator would turn a direct child into a path that leaves the backup folder.
        if not filename or "/" in filename or not filename.endswith(".gz"):
            continue

        lastmod_match = _LASTMOD_PATTERN.search(resp_block)
        length_match = _LENGTH_PATTERN.search(resp_block)

        modified = datetime.now(UTC)
        if lastmod_match:
            try:
                modified = parsedate_to_datetime(lastmod_match.group(1))
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                pass  # an unreadable date keeps the listing time

        size = 0
        if length_match:
            try:
                size = int(length_match.group(1))
            except ValueError:
                pass

        results.append(RemoteBackupFile(file_name=filename, modified_time=modified, size_bytes=size))

    return results
