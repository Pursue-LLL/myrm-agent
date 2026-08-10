"""业务层工件处理器

[INPUT]
- myrm_agent_harness.agent.artifacts::ArtifactInfo, infer_artifact_type (POS: Harness artifact types)
- app.core.artifacts.listener::upsert_processor_artifact, resolve_sandbox_file_path (POS: Deploy DB rows + sandbox path resolution)
- app.core.storage::FilesService (POS: File reference persistence)
- app.services.artifacts.share_token::is_shareable_artifact (POS: Share eligibility for oversized artifacts)

[OUTPUT]
- LocalArtifactProcessor.process_artifacts_ready: artifacts SSE event (emit only after successful DB upsert)
- PersistResult: file_id, file_size, resolved_path from persist

[POS]
Local-mode artifact processor: reference-only persist, resolved_path SSOT for IM deliverable deep links.
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

logger = logging.getLogger(__name__)

MAX_ARTIFACT_SIZE_BYTES = 5 * 1024 * 1024


@dataclass
class PersistResult:
    """持久化结果"""

    file_id: str
    file_size: int
    resolved_path: str | None = None


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
        processed_entries: list[tuple[str, str, str, str | None]] = []

        for item in artifacts_data:
            filename = item.get("filename", "")
            file_path = item.get("path", "")
            short_file_id = item.get("short_file_id")

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
                    preview_url=self._build_artifact_url(result.file_id, inline=True, content_type=content_type),
                    download_url=self._build_artifact_url(result.file_id, inline=False, content_type=content_type),
                    language=infer_language(filename),
                    created_at=datetime.now(UTC).isoformat(),
                    file_path=(
                        result.resolved_path
                        if result.resolved_path is not None
                        else self._resolve_file_path(file_path)
                    ),
                    short_file_id=str(short_file_id) if isinstance(short_file_id, str) and short_file_id else None,
                )
                artifacts.append(artifact)
                processed_entries.append(
                    (filename, file_path, result.file_id, result.resolved_path),
                )
                logger.info(f"📦 处理工件: {filename} ({artifact_type.value}, {result.file_size} bytes)")

            except Exception as e:
                logger.warning(f"📦 处理工件失败: {file_path}, error: {e}")

        if not artifacts:
            return None

        if processed_entries:
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

            upserted_file_ids: set[str] = set()
            try:
                async with get_session() as db:
                    for filename, file_path, file_id, resolved_path in processed_entries:
                        try:
                            await upsert_processor_artifact(
                                db,
                                file_id=file_id,
                                filename=filename,
                                sandbox_path=file_path,
                                workspace_root=workspace_root,
                                chat_id=self.chat_id,
                                physical_path=resolved_path,
                            )
                            upserted_file_ids.add(file_id)
                        except Exception as exc:
                            logger.error(
                                "Failed to upsert processor artifact %s (%s): %s",
                                file_id,
                                filename,
                                exc,
                            )
            except Exception as e:
                logger.error("Failed to open DB session for processor artifacts: %s", e)

            if upserted_file_ids != {entry[2] for entry in processed_entries}:
                artifacts = [artifact for artifact in artifacts if artifact.id in upserted_file_ids]

        if not artifacts:
            return None

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
            PersistResult(file_id, file_size, resolved_path) 或 None（跳过该文件）
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

    def _build_artifact_url(self, file_id: str, inline: bool = True, content_type: str = "") -> str:
        """构建工件访问 URL

        对活跃内容（HTML/SVG/XHTML）强制设置 inline=false，防止 XSS。
        """
        from myrm_agent_harness.agent.artifacts.constants import is_active_content

        force_download = is_active_content(content_type)
        url = f"{self.api_prefix}/storage/files/{file_id}/content?user_id=sandbox"
        if not inline or force_download:
            url += "&inline=false"
        return url


class LocalArtifactProcessor(BaseArtifactProcessor):
    """本地模式工件处理器

    零复制：仅记录路径引用，不上传内容。
    文件已在本地沙箱中，天然持久化。
    """

    def _local_workspace_root(self) -> str:
        from myrm_agent_harness.toolkits.code_execution.executors.base import (
            get_executor,
        )

        from app.platform_utils.workspace_root import get_workspace_root

        executor = get_executor()
        return executor.workspace_path if executor else str(get_workspace_root())

    async def _persist_file(
        self,
        filename: str,
        file_path: str,
        content_type: str,
        read_content: Callable[[str], Awaitable[bytes]] | None,
    ) -> PersistResult | None:
        import os

        from app.core.artifacts.listener import resolve_sandbox_file_path
        from app.core.storage import FilesService
        from app.services.artifacts.share_token import is_shareable_artifact

        _ = read_content  # local mode uses stat-only sizing; harness may still pass read_content

        workspace_root = self._local_workspace_root()
        resolved = resolve_sandbox_file_path(
            file_path,
            workspace_root,
            self.chat_id,
        )
        if resolved is None:
            logger.warning("📦 [Local] Generated file not found on disk: %s", file_path)
            return None

        try:
            file_size = os.path.getsize(resolved)
        except OSError as exc:
            logger.warning(
                "📦 [Local] Failed to stat generated file: %s, error: %s",
                file_path,
                exc,
            )
            return None

        if file_size > MAX_ARTIFACT_SIZE_BYTES:
            if not is_shareable_artifact(filename):
                size_mb = file_size / 1024 / 1024
                logger.warning(
                    "📦 [Local] Skipping oversized non-shareable file: %s (%.2fMB > 5MB)",
                    filename,
                    size_mb,
                )
                return None
            logger.info(
                "📦 [Local] Reference-only persist for oversized shareable artifact: %s (%.2fMB)",
                filename,
                file_size / 1024 / 1024,
            )

        files_svc = FilesService()
        file = await files_svc.save_file_reference(
            chat_id=self.chat_id,
            filename=filename,
            sandbox_path=file_path,
            file_size=file_size,
            content_type=content_type,
        )
        return PersistResult(
            file_id=file.id,
            file_size=file_size,
            resolved_path=resolved,
        )


__all__ = [
    "BaseArtifactProcessor",
    "LocalArtifactProcessor",
    "PersistResult",
]
