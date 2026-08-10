"""工件系统集成测试

测试目标：
1. 框架层 emit_artifacts_ready_event 正确发出 ARTIFACTS_READY 事件
2. 业务层 LocalArtifactProcessor 正确处理 ARTIFACTS_READY 事件
3. 懒加载机制：read_content 按需调用
"""

from __future__ import annotations

from typing import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.streaming.types import AgentEventType


class TestArtifactReadyEvent:
    """测试框架层 artifacts_ready 事件生成"""

    @pytest.mark.asyncio
    async def test_emit_artifacts_ready_event_with_files(self) -> None:
        """测试有文件时正确发出 artifacts_ready 事件"""
        from myrm_agent_harness.agent.artifacts import ArtifactRegistry
        from myrm_agent_harness.agent.streaming.artifact_events import emit_artifacts_ready_event
        from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor

        mock_executor = AsyncMock()
        mock_executor.read_file_bytes = AsyncMock(return_value=b"test content")

        artifact_registry = ArtifactRegistry()
        artifact_registry.add_files(["/workspace/test.txt", "/workspace/image.png"])

        context: dict[str, object] = {}

        set_executor(mock_executor)
        try:
            with patch(
                "myrm_agent_harness.agent.streaming.artifact_events.get_artifact_registry", return_value=artifact_registry
            ):
                events: list[dict[str, object]] = []
                async for event in emit_artifacts_ready_event("test_msg_id", context):
                    events.append(event)
        finally:
            set_executor(None)

        assert len(events) == 1
        event = events[0]
        assert event["type"] == AgentEventType.ARTIFACTS_READY.value
        assert event["message_id"] == "test_msg_id"
        assert "read_content" in event
        assert callable(event["read_content"])

        data = event["data"]
        assert isinstance(data, list)
        assert len(data) == 2

        filenames = {item["filename"] for item in data}
        assert "test.txt" in filenames
        assert "image.png" in filenames

    @pytest.mark.asyncio
    async def test_emit_artifacts_ready_event_empty(self) -> None:
        """测试无文件时不发出事件"""
        from myrm_agent_harness.agent.artifacts import ArtifactRegistry
        from myrm_agent_harness.agent.streaming.artifact_events import emit_artifacts_ready_event
        from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor

        mock_executor = AsyncMock()
        artifact_registry = ArtifactRegistry()

        context: dict[str, object] = {}

        set_executor(mock_executor)
        try:
            with patch(
                "myrm_agent_harness.agent.streaming.artifact_events.get_artifact_registry", return_value=artifact_registry
            ):
                events: list[dict[str, object]] = []
                async for event in emit_artifacts_ready_event("test_msg_id", context):
                    events.append(event)
        finally:
            set_executor(None)

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_read_content_function(self) -> None:
        """测试 read_content 函数正确读取文件"""
        from myrm_agent_harness.agent.artifacts import ArtifactRegistry
        from myrm_agent_harness.agent.streaming.artifact_events import emit_artifacts_ready_event
        from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor

        test_content = b"Hello, World!"
        mock_executor = AsyncMock()
        mock_executor.read_file_bytes = AsyncMock(return_value=test_content)

        artifact_registry = ArtifactRegistry()
        artifact_registry.add_files(["/workspace/hello.txt"])

        context: dict[str, object] = {}

        set_executor(mock_executor)
        try:
            with patch(
                "myrm_agent_harness.agent.streaming.artifact_events.get_artifact_registry", return_value=artifact_registry
            ):
                events: list[dict[str, object]] = []
                async for event in emit_artifacts_ready_event("msg_123", context):
                    events.append(event)
        finally:
            set_executor(None)

        assert len(events) == 1
        event = events[0]

        read_content: Callable[[str], Awaitable[bytes]] = event["read_content"]  # type: ignore
        content = await read_content("/workspace/hello.txt")

        assert content == test_content
        mock_executor.read_file_bytes.assert_called_once_with("/workspace/hello.txt")


class TestLocalArtifactProcessor:
    """测试 LocalArtifactProcessor（本地模式）"""

    @pytest.mark.asyncio
    async def test_local_processor_saves_reference(self, tmp_path) -> None:  # noqa: ANN001
        """本地模式应保存路径引用而非文件内容"""
        from app.core.artifacts import LocalArtifactProcessor

        output = tmp_path / "output.py"
        output.write_text("print('hi')", encoding="utf-8")

        processor = LocalArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "output.py", "path": "output.py", "type": "code"}],
            "read_content": AsyncMock(),
            "message_id": "msg_local",
        }

        mock_file = MagicMock()
        mock_file.id = "local_file_id"

        mock_executor = MagicMock()
        mock_executor.workspace_path = str(tmp_path)

        with (
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
            patch(
                "app.core.storage.service.FilesService.save_file_reference",
                new_callable=AsyncMock,
            ) as mock_save_ref,
        ):
            mock_save_ref.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        assert result["type"] == "artifacts"
        mock_save_ref.assert_called_once()

        call_kwargs = mock_save_ref.call_args
        assert call_kwargs.kwargs["sandbox_path"] == "output.py"

    @pytest.mark.asyncio
    async def test_local_processor_large_non_shareable_skipped(self, tmp_path) -> None:  # noqa: ANN001
        """本地模式下超大不可分享文件应被跳过"""
        from app.core.artifacts import LocalArtifactProcessor

        blob = tmp_path / "huge.bin"
        blob.write_bytes(b"x" * (6 * 1024 * 1024))

        processor = LocalArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "huge.bin", "path": "huge.bin", "type": "binary"}],
            "read_content": AsyncMock(),
            "message_id": "msg_big_local",
        }

        mock_executor = MagicMock()
        mock_executor.workspace_path = str(tmp_path)

        with (
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
            patch(
                "app.core.storage.service.FilesService.save_file_reference",
                new_callable=AsyncMock,
            ) as mock_save_ref,
        ):
            result = await processor.process_artifacts_ready(event)

        assert result is None
        mock_save_ref.assert_not_called()

    @pytest.mark.asyncio
    async def test_html_artifact_forces_download_on_preview_url(self, tmp_path) -> None:  # noqa: ANN001
        """HTML 文件的 preview_url 应强制 inline=false"""
        from app.core.artifacts import LocalArtifactProcessor

        page = tmp_path / "page.html"
        page.write_text("<html><body>Hello</body></html>", encoding="utf-8")

        processor = LocalArtifactProcessor(chat_id="c1", api_prefix="/api/v1")
        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "page.html", "path": "page.html", "type": "html"}],
            "read_content": AsyncMock(),
            "message_id": "msg_html",
        }

        mock_file = MagicMock()
        mock_file.id = "html_file_id"
        mock_executor = MagicMock()
        mock_executor.workspace_path = str(tmp_path)

        with (
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
            patch(
                "app.core.storage.service.FilesService.save_file_reference",
                new_callable=AsyncMock,
            ) as mock_save_ref,
        ):
            mock_save_ref.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert "inline=false" in artifact["preview_url"]
        assert "inline=false" in artifact["download_url"]

    @pytest.mark.asyncio
    async def test_plain_text_allows_inline(self, tmp_path) -> None:  # noqa: ANN001
        """纯文本文件 preview_url 应允许 inline"""
        from app.core.artifacts import LocalArtifactProcessor

        note = tmp_path / "note.txt"
        note.write_text("Hello World", encoding="utf-8")

        processor = LocalArtifactProcessor(chat_id="c1", api_prefix="/api/v1")
        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "note.txt", "path": "note.txt", "type": "document"}],
            "read_content": AsyncMock(),
            "message_id": "msg_txt",
        }

        mock_file = MagicMock()
        mock_file.id = "txt_file_id"
        mock_executor = MagicMock()
        mock_executor.workspace_path = str(tmp_path)

        with (
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
            patch(
                "app.core.storage.service.FilesService.save_file_reference",
                new_callable=AsyncMock,
            ) as mock_save_ref,
        ):
            mock_save_ref.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert "inline=false" not in artifact["preview_url"]

    @pytest.mark.asyncio
    async def test_local_processor_ignores_system_files(self) -> None:
        """本地模式下系统文件应被忽略"""
        from app.core.artifacts import LocalArtifactProcessor

        processor = LocalArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [
                {"filename": ".DS_Store", "path": "/workspace/.DS_Store", "type": "binary"},
                {"filename": "__pycache__", "path": "/workspace/__pycache__", "type": "binary"},
            ],
            "read_content": AsyncMock(),
            "message_id": "msg_sys",
        }

        result = await processor.process_artifacts_ready(event)
        assert result is None


class TestLocalSpreadsheetArtifactIntegration:
    """本地模式下 spreadsheet artifact 全链路集成测试"""

    @pytest.mark.asyncio
    async def test_local_csv_artifact_type(self, tmp_path) -> None:  # noqa: ANN001
        """本地模式下 CSV 文件也能正确推断为 spreadsheet"""
        from app.core.artifacts import LocalArtifactProcessor

        csv_file = tmp_path / "local.csv"
        csv_file.write_text("id,name\n1,Alice", encoding="utf-8")

        processor = LocalArtifactProcessor(chat_id="test_local_csv", api_prefix="/api/v1")

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "local.csv", "path": "local.csv", "type": "document"}],
            "read_content": AsyncMock(),
            "message_id": "msg_local_csv",
        }

        mock_file = MagicMock()
        mock_file.id = "local_csv_id"
        mock_executor = MagicMock()
        mock_executor.workspace_path = str(tmp_path)

        with (
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
            patch(
                "app.core.storage.service.FilesService.save_file_reference",
                new_callable=AsyncMock,
            ) as mock_save_ref,
        ):
            mock_save_ref.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert artifact["type"] == "spreadsheet"
        assert artifact["filename"] == "local.csv"

    @pytest.mark.asyncio
    async def test_local_xls_artifact_type(self, tmp_path) -> None:  # noqa: ANN001
        """本地模式下 .xls 文件正确推断为 spreadsheet"""
        from app.core.artifacts import LocalArtifactProcessor

        xls_file = tmp_path / "legacy.xls"
        xls_file.write_bytes(b"\xd0\xcf\x11\xe0fake-xls")

        processor = LocalArtifactProcessor(chat_id="test_local_xls", api_prefix="/api/v1")

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "legacy.xls", "path": "legacy.xls", "type": "binary"}],
            "read_content": AsyncMock(),
            "message_id": "msg_local_xls",
        }

        mock_file = MagicMock()
        mock_file.id = "local_xls_id"
        mock_executor = MagicMock()
        mock_executor.workspace_path = str(tmp_path)

        with (
            patch(
                "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
                return_value=mock_executor,
            ),
            patch(
                "app.core.storage.service.FilesService.save_file_reference",
                new_callable=AsyncMock,
            ) as mock_save_ref,
        ):
            mock_save_ref.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert artifact["type"] == "spreadsheet"


class TestArtifactRegistry:
    """测试 ArtifactRegistry"""

    def test_add_files_and_get_all(self) -> None:
        """测试添加文件和获取所有文件"""
        from myrm_agent_harness.agent.artifacts import ArtifactRegistry

        registry = ArtifactRegistry()

        # 添加文件
        registry.add_files(["/workspace/doc.pdf", "/workspace/chart.png"])

        # 获取文件
        files = registry.get_all_files()

        assert len(files) == 2

        # 验证文件信息
        paths = [f.path for f in files]
        assert "/workspace/doc.pdf" in paths
        assert "/workspace/chart.png" in paths

    def test_add_files_dedup(self) -> None:
        """测试添加重复文件时自动去重"""
        from myrm_agent_harness.agent.artifacts import ArtifactRegistry

        registry = ArtifactRegistry()

        # 添加相同文件两次
        registry.add_files(["/workspace/test.txt"])
        registry.add_files(["/workspace/test.txt"])

        # 应该只有一个
        files = registry.get_all_files()
        assert len(files) == 1

    def test_add_files_ignore_system_files(self) -> None:
        """测试忽略系统文件"""
        from myrm_agent_harness.agent.artifacts import ArtifactRegistry

        registry = ArtifactRegistry()

        # 添加系统文件
        registry.add_files(
            [
                "/workspace/.DS_Store",
                "/workspace/__pycache__/test.pyc",
                "/workspace/normal.txt",
            ]
        )

        # 系统文件应被忽略
        files = registry.get_all_files()
        assert len(files) == 1
        assert files[0].path == "/workspace/normal.txt"
