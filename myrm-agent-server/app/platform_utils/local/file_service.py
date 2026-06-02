"""本地文件服务

本地模式专用的文件服务。

核心理念：沙箱即存储
- 文件已在本地磁盘，无需上传
- 只记录文件引用（路径）
- 元数据保存在本地
"""

import json
import logging
import mimetypes
import os
from datetime import datetime
from typing import cast

import nanoid
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.storage.models import File, FilePurpose

logger = logging.getLogger(__name__)


class LocalFileService:
    """本地文件服务

    实现 FileService Protocol，用于本地模式。

    特点：
    - 沙箱即存储：文件已在本地，只记录引用
    - 元数据本地存储：使用 JSON 文件
    - 零网络上传
    """

    def __init__(self, storage: LocalStorageBackend | None = None):
        """初始化本地文件服务

        Args:
            storage: 本地存储后端，如果不提供则自动创建
        """
        if storage is None:
            # 默认存储路径
            default_path = os.path.expanduser("/workspace/storage")
            storage = LocalStorageBackend(default_path)
        self._storage = storage

    def _generate_file_id(self) -> str:
        """生成文件 ID"""
        return f"file_{nanoid.generate(size=12)}"

    def _get_metadata_path(self, file_id: str) -> str:
        """获取元数据文件路径"""
        return f"metadata/files/{file_id}.json"

    async def save_file(
        self,
        chat_id: str,
        filename: str,
        content: bytes | None = None,
        sandbox_path: str | None = None,
    ) -> File:
        """保存文件

        本地模式：使用 sandbox_path，忽略 content

        Args:
            chat_id: 会话 ID
            filename: 文件名
            content: 文件内容（本地模式忽略）
            sandbox_path: 沙箱内的文件路径

        Returns:
            文件对象

        Raises:
            ValueError: 如果 sandbox_path 未提供
        """
        if not sandbox_path:
            raise ValueError("Local mode requires sandbox_path. Use content parameter for sandbox mode.")

        # 生成文件 ID
        file_id = self._generate_file_id()

        # 构建存储路径
        # 格式：sandboxes/{user_id}/{chat_id}/{relative_path}
        relative_path = sandbox_path.lstrip("/").replace("workspace/", "")
        storage_path = f"sandboxes/{chat_id}/{relative_path}"

        # 获取文件大小
        abs_path = self._storage.resolve_absolute_path(storage_path)
        file_size = 0
        if os.path.exists(abs_path):
            file_size = os.path.getsize(abs_path)

        # 推断 MIME 类型
        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or "application/octet-stream"

        # 创建文件对象
        file = File(
            id=file_id,
            purpose=FilePurpose.GENERATED,
            filename=filename,
            content_type=content_type,
            size=file_size,
            storage_path=storage_path,
            source_chat_id=chat_id,
        )

        # 保存元数据
        metadata_path = self._get_metadata_path(file_id)
        await self._storage.write_text(metadata_path, json.dumps(file.to_dict(), indent=2, ensure_ascii=False))

        logger.warning(f"✅ 保存文件引用: {file_id} ({filename}) -> {storage_path}")
        return file

    async def upload_file(
        self,
        filename: str,
        content: bytes,
    ) -> File:
        """上传文件（本地模式也支持直接上传）

        用于用户主动上传的文件（非沙箱生成）。

        Args:
            filename: 文件名
            content: 文件内容

        Returns:
            文件对象
        """
        file_id = self._generate_file_id()

        # 存储路径
        storage_path = f"uploads/{file_id}/{filename}"

        # 写入文件
        await self._storage.write(storage_path, content)

        # 推断 MIME 类型
        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or "application/octet-stream"

        # 创建文件对象
        file = File(
            id=file_id,
            purpose=FilePurpose.UPLOAD,
            filename=filename,
            content_type=content_type,
            size=len(content),
            storage_path=storage_path,
        )

        # 保存元数据
        metadata_path = self._get_metadata_path(file_id)
        await self._storage.write_text(metadata_path, json.dumps(file.to_dict(), indent=2, ensure_ascii=False))

        logger.warning(f"✅ 上传文件: {file_id} ({filename}, {len(content)} bytes)")
        return file

    async def get_file(self, file_id: str) -> File | None:
        """获取文件信息

        Args:
            file_id: 文件 ID

        Returns:
            文件对象，如果不存在返回 None
        """
        metadata_path = self._get_metadata_path(file_id)

        try:
            content = await self._storage.read_text(metadata_path)
            file = File.from_dict(json.loads(content))

            # 检查是否过期
            if file.expires_at and file.expires_at < datetime.utcnow():
                return None

            return file
        except FileNotFoundError:
            return None

    async def get_content(self, file_id: str) -> bytes:
        """获取文件内容

        Args:
            file_id: 文件 ID

        Returns:
            文件内容

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权访问
        """
        file = await self.get_file(file_id)
        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")

        return cast(bytes, await self._storage.read(file.storage_path))

    async def delete_file(self, file_id: str) -> bool:
        """删除文件

        Args:
            file_id: 文件 ID

        Returns:
            是否删除成功
        """
        file = await self.get_file(file_id)
        if not file:
            return False

        # 删除文件内容
        try:
            await self._storage.delete(file.storage_path)
        except FileNotFoundError:
            pass

        # 删除元数据
        metadata_path = self._get_metadata_path(file_id)
        try:
            await self._storage.delete(metadata_path)
        except FileNotFoundError:
            pass

        logger.warning(f"🗑️ 删除文件: {file_id}")
        return True

    async def list_files(self) -> list[File]:
        """列出用户文件

        Args:

        Returns:
            文件列表
        """
        files: list[File] = []
        now = datetime.utcnow()

        # 遍历元数据目录
        metadata_files = await self._storage.list("metadata/files")

        for metadata_path in metadata_files:
            if not metadata_path.endswith(".json"):
                continue

            try:
                content = await self._storage.read_text(metadata_path)
                file = File.from_dict(json.loads(content))

                # 过滤：排除过期文件
                if file.expires_at and file.expires_at < now:
                    continue

                files.append(file)
            except Exception as e:
                logger.warning(f"Failed to load file metadata from {metadata_path}: {e}")

        return files

    async def get_file_url(self, file_id: str) -> str:
        """获取文件访问 URL

        Args:
            file_id: 文件 ID

        Returns:
            文件 URL（file:// 协议）

        Raises:
            FileNotFoundError: 文件不存在
        """
        file = await self.get_file(file_id)
        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")

        return cast(str, await self._storage.get_url(file.storage_path))
