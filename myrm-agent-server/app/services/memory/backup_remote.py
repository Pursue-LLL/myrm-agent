"""Remote backup strategies for cloud storage (WebDAV / S3).

Implements backup upload/download/list/delete operations for:
- WebDAV (坚果云 / Nextcloud / 自建等)
- S3-compatible storage (AWS S3 / MinIO / 阿里云 OSS 等)

Used by the auto-backup scheduler and remote backup API endpoints.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoteBackupFile:
    """Metadata for a remote backup file."""

    file_name: str
    modified_time: datetime
    size_bytes: int


@dataclass
class RemoteBackupConfig:
    """Base configuration for remote backup."""

    enabled: bool = False
    auto_sync: bool = False
    sync_interval_minutes: int = 60
    max_backups: int = 10
    device_name: str = ""


@dataclass
class WebDAVBackupConfig(RemoteBackupConfig):
    """WebDAV-specific backup configuration."""

    host: str = ""
    username: str = ""
    password: str = ""
    path: str = "/myrm-backups"


@dataclass
class S3BackupConfig(RemoteBackupConfig):
    """S3-compatible storage backup configuration."""

    endpoint: str = ""
    region: str = ""
    bucket: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    prefix: str = "myrm-backups/"
    force_path_style: bool = True


class RemoteBackupStrategy(ABC):
    """Abstract base for remote backup operations."""

    @abstractmethod
    async def upload(self, local_path: Path, remote_name: str) -> bool:
        """Upload a local backup file to remote storage."""

    @abstractmethod
    async def download(self, remote_name: str, local_path: Path) -> bool:
        """Download a remote backup file to local path."""

    @abstractmethod
    async def list_files(self) -> list[RemoteBackupFile]:
        """List all backup files on remote storage, newest first."""

    @abstractmethod
    async def delete(self, remote_name: str) -> bool:
        """Delete a remote backup file."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Test connectivity to remote storage."""


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


class S3BackupStrategy(RemoteBackupStrategy):
    """S3-compatible storage backup strategy.

    Supports: AWS S3, MinIO, 阿里云 OSS, Cloudflare R2 etc.
    """

    def __init__(self, config: S3BackupConfig) -> None:
        self._config = config
        self._client: "_S3Client | None" = None

    def _get_client(self) -> "_S3Client":
        if self._client is None:
            self._client = _S3Client(
                endpoint=self._config.endpoint,
                region=self._config.region,
                bucket=self._config.bucket,
                access_key_id=self._config.access_key_id,
                secret_access_key=self._config.secret_access_key,
                prefix=self._config.prefix,
                force_path_style=self._config.force_path_style,
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


# ============================================================================
# Internal clients (httpx-based async implementations)
# ============================================================================


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

        results: list[RemoteBackupFile] = []
        try:
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
                if resp.status_code != 207:
                    return results
                results = _parse_webdav_multistatus(resp.text)
        except Exception as e:
            logger.error("WebDAV list error: %s", e)
        results.sort(key=lambda f: f.modified_time, reverse=True)
        return results

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


class _S3Client:
    """Async S3-compatible client using aioboto3."""

    def __init__(
        self,
        endpoint: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        prefix: str,
        force_path_style: bool,
    ) -> None:
        self._endpoint = endpoint
        self._region = region
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._prefix = prefix
        self._force_path_style = force_path_style

    def _session_kwargs(self) -> dict:
        kwargs: dict = {
            "region_name": self._region or "us-east-1",
            "aws_access_key_id": self._access_key_id,
            "aws_secret_access_key": self._secret_access_key,
        }
        if self._endpoint:
            kwargs["endpoint_url"] = self._endpoint
        return kwargs

    def _client_config(self):  # noqa: ANN202
        from botocore.config import Config as BotoConfig

        config_kwargs: dict = {"connect_timeout": 15, "read_timeout": 300}
        if self._force_path_style:
            config_kwargs["s3"] = {"addressing_style": "path"}
        return BotoConfig(**config_kwargs)

    def _key(self, remote_name: str) -> str:
        return f"{self._prefix}{remote_name}" if self._prefix else remote_name

    async def check_connection(self) -> bool:
        import aioboto3

        try:
            session = aioboto3.Session()
            async with session.client("s3", config=self._client_config(), **self._session_kwargs()) as client:
                await client.head_bucket(Bucket=self._bucket)
            return True
        except Exception as e:
            logger.warning("S3 connection check failed: %s", e)
            return False

    async def put_file(self, local_path: Path, remote_name: str) -> bool:
        import aioboto3

        try:
            session = aioboto3.Session()
            async with session.client("s3", config=self._client_config(), **self._session_kwargs()) as client:
                with open(local_path, "rb") as f:
                    await client.upload_fileobj(f, self._bucket, self._key(remote_name))
            return True
        except Exception as e:
            logger.error("S3 upload error: %s", e)
            return False

    async def get_file(self, remote_name: str, local_path: Path) -> bool:
        import aioboto3

        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            session = aioboto3.Session()
            async with session.client("s3", config=self._client_config(), **self._session_kwargs()) as client:
                with open(local_path, "wb") as f:
                    await client.download_fileobj(self._bucket, self._key(remote_name), f)
            return True
        except Exception as e:
            logger.error("S3 download error: %s", e)
            return False

    async def list_files(self) -> list[RemoteBackupFile]:
        import aioboto3

        results: list[RemoteBackupFile] = []
        try:
            session = aioboto3.Session()
            async with session.client("s3", config=self._client_config(), **self._session_kwargs()) as client:
                response = await client.list_objects_v2(
                    Bucket=self._bucket,
                    Prefix=self._prefix,
                )
                for obj in response.get("Contents", []):
                    key = obj["Key"]
                    name = key[len(self._prefix) :] if self._prefix and key.startswith(self._prefix) else key
                    if not name or name.endswith("/"):
                        continue
                    mod_time = obj["LastModified"]
                    if mod_time.tzinfo is None:
                        mod_time = mod_time.replace(tzinfo=UTC)
                    results.append(
                        RemoteBackupFile(
                            file_name=name,
                            modified_time=mod_time,
                            size_bytes=obj["Size"],
                        )
                    )
        except Exception as e:
            logger.error("S3 list error: %s", e)
        results.sort(key=lambda f: f.modified_time, reverse=True)
        return results

    async def delete_file(self, remote_name: str) -> bool:
        import aioboto3

        try:
            session = aioboto3.Session()
            async with session.client("s3", config=self._client_config(), **self._session_kwargs()) as client:
                await client.delete_object(Bucket=self._bucket, Key=self._key(remote_name))
            return True
        except Exception as e:
            logger.error("S3 delete error: %s", e)
            return False


# ============================================================================
# WebDAV XML parser
# ============================================================================


def _parse_webdav_multistatus(xml_text: str) -> list[RemoteBackupFile]:
    """Parse WebDAV PROPFIND 207 multistatus response."""
    import re
    from email.utils import parsedate_to_datetime

    results: list[RemoteBackupFile] = []

    href_pattern = re.compile(r"<[^>]*href[^>]*>([^<]+)</", re.IGNORECASE)
    lastmod_pattern = re.compile(r"<[^>]*getlastmodified[^>]*>([^<]+)</", re.IGNORECASE)
    length_pattern = re.compile(r"<[^>]*getcontentlength[^>]*>([^<]+)</", re.IGNORECASE)

    responses = re.split(r"<[^>]*response[^>]*>", xml_text, flags=re.IGNORECASE)

    for resp_block in responses[1:]:
        href_match = href_pattern.search(resp_block)
        if not href_match:
            continue
        href = href_match.group(1).strip()
        filename = href.rstrip("/").rsplit("/", 1)[-1]
        if not filename or not filename.endswith(".gz"):
            continue

        lastmod_match = lastmod_pattern.search(resp_block)
        length_match = length_pattern.search(resp_block)

        modified = datetime.now(UTC)
        if lastmod_match:
            try:
                modified = parsedate_to_datetime(lastmod_match.group(1))
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=UTC)
            except Exception:
                pass

        size = 0
        if length_match:
            try:
                size = int(length_match.group(1))
            except ValueError:
                pass

        results.append(RemoteBackupFile(file_name=filename, modified_time=modified, size_bytes=size))

    return results
