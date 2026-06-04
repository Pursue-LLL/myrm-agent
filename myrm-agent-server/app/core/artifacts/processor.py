"""业务层工件处理器

负责处理框架层发出的 artifacts_ready 事件，按需读取并持久化。
采用模板方法模式：基类实现完整的事件处理流程，子类只需实现 _persist_file() 定义持久化策略。
对活跃内容（HTML/SVG/XHTML）强制设置下载模式，防止 XSS。
"""

from __future__ import annotations

import logging
import mimetypes
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from myrm_agent_harness.agent.artifacts.types import ArtifactInfo
    from myrm_agent_harness.toolkits.storage.base import StorageProvider

logger = logging.getLogger(__name__)

MAX_ARTIFACT_SIZE_BYTES = 5 * 1024 * 1024


@dataclass
class PersistResult:
    """持久化结果"""

    file_id: str
    file_size: int


class BaseArtifactProcessor(ABC):
    """工件处理器基类（模板方法模式）

    完整实现 process_artifacts_ready 流程：
    事件解析 → 文件遍历 → 过滤 → 持久化（子类） → 构造元数据 → 返回事件

    子类只需实现 _persist_file() 定义持久化策略。
    """

    def __init__(
        self,
        chat_id: str,
        api_prefix: str = "/api/v1",
    ):
        self.chat_id = chat_id
        self.api_prefix = api_prefix

    async def process_artifacts_ready(
        self,
        event: dict[str, object],
    ) -> dict[str, object] | None:
        """处理 artifacts_ready 事件（模板方法）

        Args:
            event: artifacts_ready 事件
                - type: "artifacts_ready"
                - data: [{"filename": "...", "path": "...", "type": "..."}]
                - read_content: async function(path) -> bytes
                - message_id: "..."

        Returns:
            artifacts 事件（供前端展示），如果没有工件返回 None
        """
        from myrm_agent_harness.agent.artifacts import ArtifactInfo
        from myrm_agent_harness.agent.artifacts.types import (
            infer_artifact_type,
            infer_language,
        )

        artifacts_data = cast(list[dict[str, str]], event.get("data", []))
        read_content = cast(
            Callable[[str], Awaitable[bytes]] | None,
            event.get("read_content"),
        )
        message_id = cast(str, event.get("message_id", ""))

        if not artifacts_data:
            return None

        artifacts: list[ArtifactInfo] = []
        processed_entries: list[tuple[str, str, str]] = []

        for item in artifacts_data:
            filename = item.get("filename", "")
            file_path = item.get("path", "")

            if self._should_ignore(filename):
                logger.debug(f"📦 忽略文件: {filename}")
                continue

            try:
                content_type = self._get_content_type(filename)
                result = await self._persist_file(
                    filename=filename,
                    file_path=file_path,
                    content_type=content_type,
                    read_content=read_content,
                )
                if result is None:
                    continue

                artifact_type = infer_artifact_type(Path(filename).name)
                artifact = ArtifactInfo(
                    id=result.file_id,
                    filename=filename,
                    type=artifact_type,
                    content_type=content_type,
                    size=result.file_size,
                    preview_url=self._build_artifact_url(
                        result.file_id, inline=True, content_type=content_type
                    ),
                    download_url=self._build_artifact_url(
                        result.file_id, inline=False, content_type=content_type
                    ),
                    language=infer_language(filename),
                    created_at=datetime.now(UTC).isoformat(),
                    file_path=self._resolve_file_path(file_path),
                )
                artifacts.append(artifact)
                processed_entries.append((filename, file_path, result.file_id))
                logger.info(
                    f"📦 处理工件: {filename} ({artifact_type.value}, {result.file_size} bytes)"
                )

            except Exception as e:
                logger.warning(f"📦 处理工件失败: {file_path}, error: {e}")

        if not artifacts:
            return None

        if processed_entries:
            try:
                from myrm_agent_harness.toolkits.code_execution.executors.base import (
                    get_executor,
                )

                from app.core.artifacts.listener import upsert_processor_artifact
                from app.database.connection import get_session
                from app.platform_utils.workspace_root import get_workspace_root

                executor = get_executor()
                if executor:
                    workspace_root = executor.workspace_path
                else:
                    workspace_root = str(get_workspace_root())

                async with get_session() as db:
                    for filename, file_path, file_id in processed_entries:
                        await upsert_processor_artifact(
                            db,
                            file_id=file_id,
                            filename=filename,
                            sandbox_path=file_path,
                            workspace_root=workspace_root,
                            chat_id=self.chat_id,
                        )
            except Exception as e:
                logger.error("Failed to persist processor artifacts to DB: %s", e)

        # Registry hook — only when processor path did not persist (avoids duplicate uuid rows)
        if not processed_entries:
            try:
                from myrm_agent_harness.agent.artifacts.registry import (
                    get_artifact_registry,
                )
                from myrm_agent_harness.toolkits.code_execution.executors.base import (
                    get_executor,
                )

                from app.core.artifacts.listener import persist_artifact_event
                from app.database.connection import get_session
                from app.platform_utils.workspace_root import get_workspace_root

                registry = get_artifact_registry()
                if registry and len(registry) > 0:
                    executor = get_executor()
                    if executor:
                        workspace_root = executor.workspace_path
                    else:
                        workspace_root = str(get_workspace_root())

                    async with get_session() as db:
                        await persist_artifact_event(
                            db=db,
                            files=registry.get_all_files(),
                            workspace_root=workspace_root,
                            chat_id=self.chat_id,
                            owner_id=None,
                            tenant_id=None,
                        )
            except Exception as e:
                logger.error("Failed to persist artifacts in process_artifacts_ready: %s", e)

        return {
            "type": "artifacts",
            "data": [artifact.to_dict() for artifact in artifacts],
            "message_id": message_id,
        }

    @abstractmethod
    async def _persist_file(
        self,
        filename: str,
        file_path: str,
        content_type: str,
        read_content: Callable[[str], Awaitable[bytes]] | None,
    ) -> PersistResult | None:
        """持久化单个文件（子类实现）

        Args:
            filename: 文件名
            file_path: 沙箱内文件路径
            content_type: MIME 类型
            read_content: 懒加载读取函数（可能为 None）

        Returns:
            PersistResult(file_id, file_size) 或 None（跳过该文件）
        """
        ...

    def _should_ignore(self, filename: str) -> bool:
        """检查是否应该忽略文件"""
        from myrm_agent_harness.agent.artifacts.filters import (
            should_filter_skill_resource,
            should_ignore_artifact,
        )

        filename_only = Path(filename).name
        if should_ignore_artifact(filename_only):
            return True

        if should_filter_skill_resource(filename):
            return True

        return False

    def _get_content_type(self, filename: str) -> str:
        """获取 MIME 类型"""
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or "application/octet-stream"

    def _resolve_file_path(self, sandbox_path: str) -> str | None:
        """Resolve artifact file path for client display.

        Subclasses override to return a user-visible local path (e.g. LocalArtifactProcessor).
        Default returns None — sandbox-internal paths are not exposed to the client.
        """
        return None

    def _build_artifact_url(
        self, file_id: str, inline: bool = True, content_type: str = ""
    ) -> str:
        """构建工件访问 URL

        对活跃内容（HTML/SVG/XHTML）强制设置 inline=false，防止 XSS。
        """
        from myrm_agent_harness.agent.artifacts.constants import is_active_content

        force_download = is_active_content(content_type)
        url = f"{self.api_prefix}/storage/files/{file_id}/content?user_id=sandbox"
        if not inline or force_download:
            url += "&inline=false"
        return url


class ArtifactProcessor(BaseArtifactProcessor):
    """业务层工件处理器（Sandbox 模式）

    读取文件内容 → 上传到云存储 → 返回持久化结果。
    """

    def __init__(
        self,
        chat_id: str,
        api_prefix: str = "/api/v1",
        storage_backend: StorageProvider | None = None,
    ):
        super().__init__(chat_id, api_prefix)
        self._storage_backend = storage_backend

    async def _persist_file(
        self,
        filename: str,
        file_path: str,
        content_type: str,
        read_content: Callable[[str], Awaitable[bytes]] | None,
    ) -> PersistResult | None:
        if read_content is None:
            return None

        from app.core.storage import FilesService

        content = await read_content(file_path)
        if content is None:
            logger.warning(f"📦 无法读取文件: {file_path}")
            return None

        if len(content) > MAX_ARTIFACT_SIZE_BYTES:
            size_mb = len(content) / 1024 / 1024
            logger.warning(f"📦 跳过大文件: {filename} ({size_mb:.2f}MB > 5MB)")
            return None

        files_svc = FilesService(storage=self._storage_backend)
        file = await files_svc.save_generated_file(
            filename=filename,
            content=content,
            content_type=content_type,
            source_chat_id=self.chat_id,
        )
        return PersistResult(file_id=file.id, file_size=len(content))


class LocalArtifactProcessor(BaseArtifactProcessor):
    """本地模式工件处理器

    零复制：仅记录路径引用，不上传内容。
    文件已在本地沙箱中，天然持久化。
    """

    def _resolve_file_path(self, sandbox_path: str) -> str | None:
        """Return the actual local filesystem path for the artifact."""
        if not sandbox_path:
            return None

        from myrm_agent_harness.toolkits.code_execution.executors.base import (
            get_executor,
        )

        executor = get_executor()
        if executor:
            import os

            return os.path.join(executor.workspace_path, sandbox_path)

        return sandbox_path

    async def _persist_file(
        self,
        filename: str,
        file_path: str,
        content_type: str,
        read_content: Callable[[str], Awaitable[bytes]] | None,
    ) -> PersistResult | None:
        from app.core.storage import FilesService

        file_size = 0
        if read_content is not None:
            try:
                content = await read_content(file_path)
                if content is not None:
                    file_size = len(content)
                    if file_size > MAX_ARTIFACT_SIZE_BYTES:
                        size_mb = file_size / 1024 / 1024
                        logger.warning(
                            f"📦 [Local] 跳过大文件: {filename} ({size_mb:.2f}MB > 5MB)"
                        )
                        return None
            except Exception as e:
                logger.warning(f"📦 [Local] 获取文件大小失败: {file_path}, {e}")

        files_svc = FilesService()
        file = await files_svc.save_file_reference(
            chat_id=self.chat_id,
            filename=filename,
            sandbox_path=file_path,
            file_size=file_size,
            content_type=content_type,
        )
        return PersistResult(file_id=file.id, file_size=file_size)


__all__ = [
    "ArtifactProcessor",
    "BaseArtifactProcessor",
    "LocalArtifactProcessor",
    "PersistResult",
]
