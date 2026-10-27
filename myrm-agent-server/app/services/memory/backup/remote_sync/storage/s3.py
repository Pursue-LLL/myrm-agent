"""S3-compatible backup storage (AWS S3, MinIO, Alibaba OSS, Cloudflare R2 ...) over aioboto3.

[INPUT]
aioboto3 / botocore (POS: S3 client, imported on first use)
app.services.memory.backup.remote_sync.storage.base::RemoteBackupStrategy/RemoteBackupFile (POS: provider contract)

[OUTPUT]
S3BackupConfig / S3BackupStrategy: the S3 implementation of the storage contract

[POS]
Lists a single page (up to 1000 objects); a listing the bucket refuses raises the transport error instead of reading as
an empty bucket.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, NotRequired, TypedDict

from app.services.memory.backup.remote_sync.storage.base import RemoteBackupFile, RemoteBackupStrategy

if TYPE_CHECKING:
    from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)


class _SessionKwargs(TypedDict):
    """The connection arguments handed to aioboto3; the endpoint is omitted (not empty) for AWS itself."""

    region_name: str
    aws_access_key_id: str
    aws_secret_access_key: str
    endpoint_url: NotRequired[str]


@dataclass
class S3BackupConfig:
    """S3-compatible storage connection settings."""

    endpoint: str = ""
    region: str = ""
    bucket: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    prefix: str = "myrm-backups/"
    force_path_style: bool = True


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

    def _session_kwargs(self) -> _SessionKwargs:
        kwargs: _SessionKwargs = {
            "region_name": self._region or "us-east-1",
            "aws_access_key_id": self._access_key_id,
            "aws_secret_access_key": self._secret_access_key,
        }
        if self._endpoint:
            kwargs["endpoint_url"] = self._endpoint
        return kwargs

    def _client_config(self) -> BotoConfig:
        from botocore.config import Config as BotoConfig

        config_kwargs: dict[str, int | dict[str, str]] = {"connect_timeout": 15, "read_timeout": 300}
        if self._force_path_style:
            config_kwargs["s3"] = {"addressing_style": "path"}
        return BotoConfig(**config_kwargs)

    @asynccontextmanager
    async def _client(self):
        # aioboto3 ships no type stubs: its client factory is inferred as a sync client although it returns
        # an async context manager.
        import aioboto3

        session = aioboto3.Session()
        s3 = session.client("s3", config=self._client_config(), **self._session_kwargs())
        async with s3 as client:  # pyright: ignore[reportGeneralTypeIssues]
            yield client

    def _key(self, remote_name: str) -> str:
        return f"{self._prefix}{remote_name}" if self._prefix else remote_name

    async def check_connection(self) -> bool:
        try:
            async with self._client() as client:
                await client.head_bucket(Bucket=self._bucket)
            return True
        except Exception as e:
            logger.warning("S3 connection check failed: %s", e)
            return False

    async def put_file(self, local_path: Path, remote_name: str) -> bool:
        try:
            async with self._client() as client:
                with open(local_path, "rb") as f:
                    await client.upload_fileobj(f, self._bucket, self._key(remote_name))
            return True
        except Exception as e:
            logger.error("S3 upload error: %s", e)
            return False

    async def get_file(self, remote_name: str, local_path: Path) -> bool:
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            async with self._client() as client:
                with open(local_path, "wb") as f:
                    await client.download_fileobj(self._bucket, self._key(remote_name), f)
            return True
        except Exception as e:
            logger.error("S3 download error: %s", e)
            return False

    async def list_files(self) -> list[RemoteBackupFile]:
        results: list[RemoteBackupFile] = []
        async with self._client() as client:
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
        results.sort(key=lambda f: f.modified_time, reverse=True)
        return results

    async def delete_file(self, remote_name: str) -> bool:
        try:
            async with self._client() as client:
                await client.delete_object(Bucket=self._bucket, Key=self._key(remote_name))
            return True
        except Exception as e:
            logger.error("S3 delete error: %s", e)
            return False
