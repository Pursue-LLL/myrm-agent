"""S3 Storage Backend (业务层)

Sandbox 模式的云存储后端实现，基于 AWS S3 / Cloudflare R2。

设计原则：
- 异步操作：所有 I/O 操作使用 async/await
- 持久化连接：复用 TCP/TLS 连接，避免重建开销
- 大文件优化：>5MB 使用分片并行上传
- 自动重试：连接失败自动重连

使用示例：
    backend = S3StorageBackend(
        bucket="my-bucket",
        prefix="workspaces/",
        region="us-east-1"
    )

    # 读取
    data = await backend.read("user_123/file.txt")

    # 写入
    await backend.write("user_123/file.txt", b"content")

    # 获取签名 URL
    url = await backend.get_url("user_123/file.txt")
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from myrm_agent_harness.toolkits.storage.base import FileInfo

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client

_T = TypeVar("_T")


class _S3ClientContextManager(Protocol):
    async def __aenter__(self) -> "S3Client": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None: ...


try:
    import aioboto3
    from botocore.exceptions import ClientError as _ImportedClientError

    HAS_S3 = True
except ImportError:
    HAS_S3 = False
    aioboto3 = None

if HAS_S3:
    ClientError = _ImportedClientError
else:

    class _FallbackClientError(Exception):
        """Stub when botocore / aioboto3 is not installed."""

    ClientError = _FallbackClientError

logger = logging.getLogger(__name__)

# 性能优化常量
MULTIPART_THRESHOLD = 5 * 1024 * 1024  # 5MB 以上使用分片上传
MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024  # 8MB 分片大小（R2 最小 5MB）
MAX_CONCURRENT_PARTS = 4  # 最大并行分片数
CONNECTION_RETRY_ATTEMPTS = 3  # 连接重试次数


class S3StorageBackend:
    """S3 存储后端

    将文件存储在 AWS S3 / Cloudflare R2 中。
    适用于：Sandbox 模式（由控制平面管理的沙箱实例）
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ):
        """初始化 S3 后端

        Args:
            bucket: S3 bucket 名称
            prefix: 路径前缀（如 "workspaces/"）
            region: AWS region
            aws_access_key_id: AWS Access Key ID（可选，默认从环境变量读取）
            aws_secret_access_key: AWS Secret Access Key（可选）
            endpoint_url: 自定义 endpoint（可选，用于 R2/MinIO 等兼容服务）
        """
        self.namespace = (prefix or None) or ""

        if not HAS_S3:
            raise ImportError(
                "aioboto3 is required for S3 backend. Run: uv sync (aioboto3 is a main dependency)"
            )

        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.region = region
        self.endpoint_url = endpoint_url

        # S3 客户端配置
        self._client_kwargs: dict[str, str] = {
            "region_name": region,
        }

        if aws_access_key_id:
            self._client_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            self._client_kwargs["aws_secret_access_key"] = aws_secret_access_key
        if endpoint_url:
            self._client_kwargs["endpoint_url"] = endpoint_url

        # Session（复用连接池）
        self._session = aioboto3.Session()

        # 持久化客户端连接（懒加载）
        self._client: "S3Client | None" = None
        self._client_lock = asyncio.Lock()
        self._client_context: _S3ClientContextManager | None = None

        # ETag 缓存（用于增量同步）
        self._etag_cache: dict[str, tuple[str, float]] = {}

        logger.warning(f"📦 S3Backend initialized: bucket={bucket}, prefix={prefix}")

    async def _get_client(self) -> "S3Client":
        """获取持久化 S3 客户端（线程安全，带自动重连）"""
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            self._client_context = cast(_S3ClientContextManager, self._session.client("s3", **self._client_kwargs))
            self._client = await self._client_context.__aenter__()
            logger.warning("🔗 S3 persistent client established")
            return self._client

    async def _reset_client(self) -> None:
        """重置客户端连接（连接失败时调用）"""
        async with self._client_lock:
            if self._client_context is not None:
                try:
                    await self._client_context.__aexit__(None, None, None)

                except Exception:
                    pass
            self._client = None
            self._client_context = None
            logger.warning("🔄 S3 client reset, will reconnect on next request")

    async def _execute_with_retry(self, operation: str, func: Callable[[S3Client], Awaitable[_T]]) -> _T:
        """执行 S3 操作，连接失败时自动重连重试"""
        for attempt in range(CONNECTION_RETRY_ATTEMPTS):
            try:
                client = await self._get_client()
                return await func(client)
            except ClientError:
                raise
            except Exception as e:
                if attempt < CONNECTION_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        f"⚠️ S3 {operation} failed (attempt {attempt + 1}/{CONNECTION_RETRY_ATTEMPTS}), reconnecting: {e}"
                    )
                    await self._reset_client()
                else:
                    logger.error(f"✗ S3 {operation} failed after {CONNECTION_RETRY_ATTEMPTS} attempts: {e}")
                    raise
        raise RuntimeError(f"S3 {operation} failed after {CONNECTION_RETRY_ATTEMPTS} attempts")

    async def close(self) -> None:
        """关闭持久化连接"""
        async with self._client_lock:
            if self._client_context is not None:
                await self._client_context.__aexit__(None, None, None)

                self._client = None
                self._client_context = None
                logger.warning("🔌 S3 persistent client closed")

    def _get_s3_key(self, path: str) -> str:
        """获取完整的 S3 key"""
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path

    # ==================== StorageProvider 协议实现 ====================

    async def read(self, path: str) -> bytes:
        """读取文件内容"""
        s3_key = self._get_s3_key(path)

        async def _read(client: "S3Client") -> bytes:
            try:
                response = await client.get_object(Bucket=self.bucket, Key=s3_key)
                async with response["Body"] as stream:
                    return cast(bytes, await stream.read())
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    raise FileNotFoundError(f"File not found in S3: {path}") from e
                raise

        return await self._execute_with_retry("read", _read)

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """读取文本文件内容"""
        content = await self.read(path)
        return content.decode(encoding)

    async def read_bytes_range(self, path: str, start: int, end: int) -> bytes:
        """Range 读取（大文件优化）"""
        s3_key = self._get_s3_key(path)

        async def _read_range(client: "S3Client") -> bytes:
            try:
                response = await client.get_object(Bucket=self.bucket, Key=s3_key, Range=f"bytes={start}-{end}")
                async with response["Body"] as stream:
                    return cast(bytes, await stream.read())
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    raise FileNotFoundError(f"File not found in S3: {path}") from e
                raise

        return await self._execute_with_retry("read_bytes_range", _read_range)

    async def write(self, path: str, data: bytes, content_type: str | None = None) -> None:
        """写入文件内容（自动选择单次上传或分片上传）"""
        if len(data) >= MULTIPART_THRESHOLD:
            await self._multipart_upload(path, data)
        else:
            await self._simple_upload(path, data)

    async def write_text(self, path: str, content: str, encoding: str = "utf-8", content_type: str | None = None) -> None:
        """写入文本文件内容"""
        await self.write(path, content.encode(encoding), content_type)

    async def _simple_upload(self, path: str, data: bytes) -> None:
        """简单上传（小文件）"""
        s3_key = self._get_s3_key(path)

        async def _upload(client: "S3Client") -> None:
            await client.put_object(Bucket=self.bucket, Key=s3_key, Body=data)

        await self._execute_with_retry("simple_upload", _upload)

    async def _multipart_upload(self, path: str, data: bytes) -> None:
        """分片并行上传（大文件，>5MB）"""
        s3_key = self._get_s3_key(path)
        client = await self._get_client()

        response = await client.create_multipart_upload(Bucket=self.bucket, Key=s3_key)
        upload_id = response["UploadId"]

        try:
            chunks = [data[i : i + MULTIPART_CHUNK_SIZE] for i in range(0, len(data), MULTIPART_CHUNK_SIZE)]
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_PARTS)

            async def upload_part(part_number: int, chunk: bytes) -> dict[str, int | str]:
                async with semaphore:
                    resp = await client.upload_part(
                        Bucket=self.bucket, Key=s3_key, PartNumber=part_number, UploadId=upload_id, Body=chunk
                    )
                    return {"PartNumber": part_number, "ETag": resp["ETag"]}

            tasks = [upload_part(i + 1, chunk) for i, chunk in enumerate(chunks)]
            parts = await asyncio.gather(*tasks)

            await client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": sorted(parts, key=lambda x: x["PartNumber"])},
            )

            logger.debug(f"✓ Multipart upload complete: {path} ({len(chunks)} parts)")

        except Exception as e:
            await client.abort_multipart_upload(Bucket=self.bucket, Key=s3_key, UploadId=upload_id)
            logger.error(f"✗ Multipart upload aborted: {path}: {e}")
            raise

    async def delete(self, path: str) -> None:
        """删除文件"""
        s3_key = self._get_s3_key(path)
        client = await self._get_client()
        await client.delete_object(Bucket=self.bucket, Key=s3_key)

    async def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        s3_key = self._get_s3_key(path)
        client = await self._get_client()

        try:
            await client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    async def list(self, prefix: str = "", recursive: bool = True) -> list[str]:
        """列出指定前缀的所有文件"""
        s3_prefix = self._get_s3_key(prefix) if prefix else self.prefix

        async def _list(client: "S3Client") -> list[str]:
            files: list[str] = []
            try:
                paginator = client.get_paginator("list_objects_v2")

                async for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
                    if "Contents" in page:
                        for obj in page["Contents"]:
                            s3_key = obj["Key"]

                            if self.prefix and s3_key.startswith(self.prefix + "/"):
                                rel_path = s3_key[len(self.prefix) + 1 :]
                                files.append(rel_path)
                            else:
                                files.append(s3_key)

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ("NoSuchKey", "NoSuchBucket"):
                    return []
                raise

            return files

        return await self._execute_with_retry("list", _list)

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """获取文件访问 URL（签名 URL）"""
        s3_key = self._get_s3_key(path)

        if not await self.exists(path):
            raise FileNotFoundError(f"File not found in S3: {path}")

        client = await self._get_client()

        url = await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )

        return cast(str, url)

    async def info(self, key: str) -> FileInfo:
        """获取文件元信息"""
        s3_key = self._get_s3_key(key)

        async def _info(client: "S3Client") -> FileInfo:
            try:
                resp = await client.head_object(Bucket=self.bucket, Key=s3_key)
                return FileInfo(
                    key=key,
                    size=resp["ContentLength"],
                    last_modified=resp.get("LastModified", datetime.now(timezone.utc)),
                    content_type=resp.get("ContentType"),
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    raise FileNotFoundError(f"File not found in S3: {key}") from e
                raise

        return await self._execute_with_retry("info", _info)

    async def copy(self, src_key: str, dst_key: str) -> None:
        """复制文件（S3 服务端复制，零流量）"""
        src_s3 = self._get_s3_key(src_key)
        dst_s3 = self._get_s3_key(dst_key)

        async def _copy(client: "S3Client") -> None:
            try:
                await client.copy_object(
                    Bucket=self.bucket,
                    CopySource={"Bucket": self.bucket, "Key": src_s3},
                    Key=dst_s3,
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    raise FileNotFoundError(f"Source file not found in S3: {src_key}") from e
                raise

        await self._execute_with_retry("copy", _copy)

    async def move(self, src_key: str, dst_key: str) -> None:
        """移动文件（copy + delete）"""
        await self.copy(src_key, dst_key)
        await self.delete(src_key)

    # ==================== 扩展方法 ====================

    async def list_files_with_etags(self, prefix: str) -> dict[str, str]:
        """列出文件及其 ETag（用于增量同步）"""
        s3_prefix = self._get_s3_key(prefix) if prefix else self.prefix
        client = await self._get_client()

        result: dict[str, str] = {}

        try:
            paginator = client.get_paginator("list_objects_v2")

            async for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        s3_key = obj["Key"]
                        etag = obj["ETag"].strip('"')

                        if self.prefix and s3_key.startswith(self.prefix + "/"):
                            rel_path = s3_key[len(self.prefix) + 1 :]
                            result[rel_path] = etag
                        else:
                            result[s3_key] = etag

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("NoSuchKey", "NoSuchBucket"):
                return {}
            raise

        return result

    async def get_size(self, path: str) -> int:
        """获取文件大小"""
        s3_key = self._get_s3_key(path)
        client = await self._get_client()

        try:
            response = await client.head_object(Bucket=self.bucket, Key=s3_key)
            return int(response["ContentLength"])

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise FileNotFoundError(f"File not found in S3: {path}") from e
            raise

    async def batch_upload(self, files: Sequence[tuple[str, bytes]]) -> None:
        """批量上传文件"""
        client = await self._get_client()

        tasks = [client.put_object(Bucket=self.bucket, Key=self._get_s3_key(path), Body=data) for path, data in files]

        await asyncio.gather(*tasks)
        logger.warning(f"✓ Batch uploaded {len(files)} files to S3")

    @staticmethod
    def compute_content_hash(data: bytes) -> str:
        """计算内容哈希（用于增量同步比对）"""
        return hashlib.md5(data).hexdigest()


__all__ = ["S3StorageBackend"]
