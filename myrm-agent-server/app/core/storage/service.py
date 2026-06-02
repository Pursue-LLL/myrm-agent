"""文件服务

提供文件的增删改查功能。
"""

from __future__ import annotations

import json
import logging
import mimetypes
from datetime import datetime, timedelta

import nanoid
from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.toolkits.storage.paths import (
    FILE_METADATA_SUFFIX,
    get_all_files_prefix,
    get_file_metadata_path,
    get_file_storage_path,
    get_user_files_prefix,
)

from app.core.storage.models import File, FilePurpose

logger = logging.getLogger(__name__)

# 默认过期时间（天）
DEFAULT_GENERATED_FILE_EXPIRY_DAYS = 7


class FilesService:
    """文件服务"""

    def __init__(self, storage: StorageProvider | None = None):
        self._storage = storage

    @property
    def storage(self) -> StorageProvider:
        """获取存储提供者（延迟初始化）"""
        if self._storage is None:
            from app.platform_utils import get_storage_provider

            self._storage = get_storage_provider()
        return self._storage

    def _generate_file_id(self) -> str:
        """生成文件 ID"""
        return f"file_{nanoid.generate(size=12)}"

    async def upload_file(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> File:
        """上传文件

        Args:
            filename: 文件名
            content: 文件内容
            content_type: MIME 类型（可选，会自动检测）

        Returns:
            创建的文件对象
        """
        # 自动检测 MIME 类型
        if content_type is None:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        # 生成 ID 和路径
        file_id = self._generate_file_id()
        storage_path = get_file_storage_path(file_id, FilePurpose.UPLOAD)

        # 创建文件对象
        file = File(
            id=file_id,
            purpose=FilePurpose.UPLOAD,
            filename=filename,
            content_type=content_type,
            size=len(content),
            storage_path=storage_path,
        )

        # 上传文件内容（统一接口：write）
        await self.storage.write(storage_path, content, content_type)

        # 保存元数据
        metadata_path = get_file_metadata_path(storage_path)
        await self.storage.write_text(metadata_path, json.dumps(file.to_dict(), indent=2))

        logger.warning(f"✅ 上传文件: {file_id} ({filename}, {len(content)} bytes)")
        return file

    async def save_file(
        self,
        chat_id: str,
        filename: str,
        content: bytes | None = None,
        sandbox_path: str | None = None,
    ) -> File:
        """保存文件（实现 FileService Protocol）

        根据参数自动选择保存方式：
        - content 提供时：上传文件内容（Sandbox 模式）
        - sandbox_path 提供时：保存文件引用（本地模式）

        Args:
            chat_id: 会话 ID
            filename: 文件名
            content: 文件内容（Sandbox 模式使用）
            sandbox_path: 本地路径（本地模式使用）

        Returns:
            文件对象

        Raises:
            ValueError: 如果 content 和 sandbox_path 都未提供
        """
        if content is not None:
            # Sandbox 模式：上传文件内容
            return await self.save_generated_file(
                filename=filename,
                content=content,
                source_chat_id=chat_id,
            )
        elif sandbox_path is not None:
            # 本地模式：保存文件引用
            return await self.save_file_reference(
                chat_id=chat_id,
                filename=filename,
                sandbox_path=sandbox_path,
                file_size=0,  # 文件大小需要从沙箱获取
            )
        else:
            raise ValueError(
                "Either content or sandbox_path must be provided. Use content for sandbox mode, sandbox_path for local mode."
            )

    async def save_generated_file(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        source_skill_id: str | None = None,
        source_chat_id: str | None = None,
        expiry_days: int | None = DEFAULT_GENERATED_FILE_EXPIRY_DAYS,
    ) -> File:
        """保存技能生成的文件

        Args:
            filename: 文件名
            content: 文件内容
            content_type: MIME 类型
            source_skill_id: 生成此文件的技能 ID
            source_chat_id: 生成此文件的会话 ID
            expiry_days: 过期天数（None 表示永不过期）

        Returns:
            创建的文件对象
        """
        # 自动检测 MIME 类型
        if content_type is None:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        # 生成 ID 和路径
        file_id = self._generate_file_id()
        storage_path = get_file_storage_path(file_id, FilePurpose.GENERATED)

        # 计算过期时间
        expires_at = None
        if expiry_days is not None:
            expires_at = datetime.utcnow() + timedelta(days=expiry_days)

        # 创建文件对象
        file = File(
            id=file_id,
            purpose=FilePurpose.GENERATED,
            filename=filename,
            content_type=content_type,
            size=len(content),
            storage_path=storage_path,
            source_skill_id=source_skill_id,
            source_chat_id=source_chat_id,
            expires_at=expires_at,
        )

        # 上传文件内容（统一接口：write）
        await self.storage.write(storage_path, content, content_type)

        # 保存元数据
        metadata_path = get_file_metadata_path(storage_path)
        await self.storage.write_text(metadata_path, json.dumps(file.to_dict(), indent=2))

        logger.warning(f"✅ 保存生成文件: {file_id} ({filename}, {len(content)} bytes)")
        return file

    async def save_file_reference(
        self,
        chat_id: str,
        filename: str,
        sandbox_path: str,
        file_size: int,
        content_type: str | None = None,
    ) -> File:
        """保存文件引用（本地模式，不上传内容）

        用于本地模式，文件已在本地磁盘中，只需记录路径引用。

        Args:
            chat_id: 聊天会话 ID
            filename: 文件名
            sandbox_path: 沙箱内的相对路径（如 /workspace/output/chart.png）
            file_size: 文件大小（字节）
            content_type: MIME 类型

        Returns:
            创建的文件对象
        """
        # 自动检测 MIME 类型
        if content_type is None:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        # 生成 ID
        file_id = self._generate_file_id()

        # 存储路径格式：sandboxes/{chat_id}/{relative_path}
        # 注意：这里不使用 get_file_storage_path，因为本地模式的路径格式不同
        relative_path = sandbox_path.lstrip("/").replace("workspace/", "")
        storage_path = f"sandboxes/{chat_id}/{relative_path}"

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

        # 只保存元数据，不上传内容（文件已在本地沙箱中）
        metadata_path = get_file_metadata_path(storage_path)
        await self.storage.write_text(metadata_path, json.dumps(file.to_dict(), indent=2))

        logger.info(f"✅ 保存文件引用: {file_id} ({filename}, {file_size} bytes) -> {storage_path}")
        return file

    async def get_file(self, file_id: str) -> File | None:
        """获取文件信息

        Args:
            file_id: 文件 ID

        Returns:
            文件对象，如果不存在返回 None
        """
        # 遍历查找文件
        # 实际应该用数据库索引
        for purpose in FilePurpose:
            if purpose == FilePurpose.SKILL:
                continue

            storage_path = get_file_storage_path(file_id, purpose)
            metadata_path = get_file_metadata_path(storage_path)
            try:
                content = await self.storage.read_text(metadata_path)
                file = File.from_dict(json.loads(content))

                # 检查是否过期
                if file.expires_at and file.expires_at < datetime.utcnow():
                    return None

                return file
            except FileNotFoundError:
                continue

        return None

    async def get_content(self, file_id: str) -> bytes:
        """获取文件内容（实现 FileService Protocol）

        Args:
            file_id: 文件 ID

        Returns:
            文件内容

        Raises:
            FileNotFoundError: 文件不存在
        """
        file = await self.get_file(file_id)
        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")

        return bytes(await self.storage.read(file.storage_path))

    async def get_file_by_id(self, file_id: str) -> File | None:
        """根据文件 ID 获取文件信息（为了保持向后兼容）

        Args:
            file_id: 文件 ID

        Returns:
            文件对象，如果不存在返回 None
        """
        return await self.get_file(file_id)

    async def get_file_content_by_path(self, storage_path: str) -> bytes | None:
        """根据存储路径获取文件内容

        Args:
            storage_path: 存储路径

        Returns:
            文件内容，如果不存在返回 None
        """
        try:
            return bytes(await self.storage.read(storage_path))
        except FileNotFoundError:
            return None

    async def list_files(
        self,
        purpose: FilePurpose | None = None,
        include_expired: bool = False,
    ) -> list[File]:
        """列出工作区的文件

        Args:
            purpose: 过滤文件用途
            include_expired: 是否包含过期文件

        Returns:
            文件列表
        """
        files: list[File] = []
        now = datetime.utcnow()

        purposes = [purpose] if purpose else [FilePurpose.UPLOAD, FilePurpose.GENERATED]

        for p in purposes:
            prefix = get_user_files_prefix(p)
            try:
                file_paths = await self.storage.list(prefix)
                for file_path in file_paths:
                    if file_path.endswith(FILE_METADATA_SUFFIX):
                        try:
                            content = await self.storage.read_text(file_path)
                            file = File.from_dict(json.loads(content))

                            # 过滤过期文件
                            if not include_expired and file.expires_at and file.expires_at < now:
                                continue

                            files.append(file)
                        except Exception as e:
                            logger.warning(f"Failed to load file from {file_path}: {e}")
            except Exception:
                pass

        return files

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
            await self.storage.delete(file.storage_path)
        except FileNotFoundError:
            pass

        # 删除元数据
        metadata_path = get_file_metadata_path(file.storage_path)
        try:
            await self.storage.delete(metadata_path)
        except FileNotFoundError:
            pass

        logger.warning(f"🗑️ 删除文件: {file_id}")
        return True

    async def cleanup_expired_files(self) -> int:
        """清理过期文件

        Returns:
            清理的文件数量
        """
        cleaned = 0
        now = datetime.utcnow()

        try:
            prefix = get_all_files_prefix()
            file_paths = await self.storage.list(prefix)

            for file_path in file_paths:
                if file_path.endswith(FILE_METADATA_SUFFIX):
                    try:
                        content = await self.storage.read_text(file_path)
                        file = File.from_dict(json.loads(content))

                        if file.expires_at and file.expires_at < now:
                            # 删除文件内容
                            try:
                                await self.storage.delete(file.storage_path)
                            except FileNotFoundError:
                                pass

                            # 删除元数据
                            try:
                                await self.storage.delete(file_path)
                            except FileNotFoundError:
                                pass

                            cleaned += 1
                            logger.warning(f"🗑️ 清理过期文件: {file.id}")
                    except Exception as e:
                        logger.warning(f"Failed to process file {file_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to cleanup expired files: {e}")

        if cleaned > 0:
            logger.warning(f"✅ 清理了 {cleaned} 个过期文件")

        return cleaned


# 全局服务实例
files_service = FilesService()
