"""工件系统集成测试

测试目标：
1. 框架层 emit_artifacts_ready_event 正确发出 ARTIFACTS_READY 事件
2. 业务层 ArtifactProcessor 正确处理 ARTIFACTS_READY 事件
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


class TestArtifactProcessor:
    """测试业务层 ArtifactProcessor"""

    @pytest.mark.asyncio
    async def test_process_artifacts_ready_basic(self) -> None:
        """测试基本的 artifacts_ready 处理"""
        from app.core.artifacts import ArtifactProcessor

        # 创建处理器
        processor = ArtifactProcessor(
            chat_id="test_chat",
            api_prefix="/api/v1",
        )

        # 创建 mock read_content
        async def mock_read_content(path: str) -> bytes:
            return b"test file content"

        # 创建 ARTIFACTS_READY 事件
        event: dict[str, object] = {
            "type": AgentEventType.ARTIFACTS_READY.value,
            "data": [
                {"filename": "test.txt", "path": "/workspace/test.txt", "type": "text"},
            ],
            "read_content": mock_read_content,
            "message_id": "msg_123",
        }

        # Mock files_service
        mock_file = MagicMock()
        mock_file.id = "file_id_123"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file

            # 执行
            result = await processor.process_artifacts_ready(event)

        # 验证
        assert result is not None
        assert result["type"] == "artifacts"
        assert result["message_id"] == "msg_123"

        data = result["data"]
        assert isinstance(data, list)
        assert len(data) == 1

        artifact = data[0]
        assert artifact["filename"] == "test.txt"
        assert "preview_url" in artifact
        assert "download_url" in artifact

    @pytest.mark.asyncio
    async def test_process_artifacts_ready_empty(self) -> None:
        """测试空数据时返回 None"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(
            chat_id="test_chat",
            api_prefix="/api/v1",
        )

        # 空数据事件
        event: dict[str, object] = {
            "type": AgentEventType.ARTIFACTS_READY.value,
            "data": [],
            "read_content": AsyncMock(),
            "message_id": "msg_123",
        }

        # 执行
        result = await processor.process_artifacts_ready(event)

        # 验证：空数据返回 None
        assert result is None

    @pytest.mark.asyncio
    async def test_lazy_loading_mechanism(self) -> None:
        """测试懒加载机制：只读取实际处理的文件"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(
            chat_id="test_chat",
            api_prefix="/api/v1",
        )

        # 创建可追踪的 read_content
        read_calls: list[str] = []

        async def tracking_read_content(path: str) -> bytes:
            read_calls.append(path)
            return b"content"

        # 创建事件
        event: dict[str, object] = {
            "type": AgentEventType.ARTIFACTS_READY.value,
            "data": [
                {"filename": "file1.txt", "path": "/workspace/file1.txt", "type": "text"},
                {"filename": "file2.txt", "path": "/workspace/file2.txt", "type": "text"},
            ],
            "read_content": tracking_read_content,
            "message_id": "msg_123",
        }

        # Mock files_service
        mock_file = MagicMock()
        mock_file.id = "file_id"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file

            # 执行
            await processor.process_artifacts_ready(event)

        # 验证：所有文件都被读取（因为都需要保存）
        assert len(read_calls) == 2
        assert "/workspace/file1.txt" in read_calls
        assert "/workspace/file2.txt" in read_calls


class TestArtifactProcessorActiveContent:
    """测试 active content 安全保护（XSS 防护）"""

    @pytest.mark.asyncio
    async def test_html_artifact_forces_download_on_preview_url(self) -> None:
        """HTML 文件的 preview_url 应强制 inline=false"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"<html><body>Hello</body></html>"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "page.html", "path": "/workspace/page.html", "type": "html"}],
            "read_content": mock_read,
            "message_id": "msg_html",
        }

        mock_file = MagicMock()
        mock_file.id = "html_file_id"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert "inline=false" in artifact["preview_url"]
        assert "inline=false" in artifact["download_url"]

    @pytest.mark.asyncio
    async def test_svg_artifact_forces_download(self) -> None:
        """SVG 文件也应强制 inline=false"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"<svg>test</svg>"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "icon.svg", "path": "/workspace/icon.svg", "type": "svg"}],
            "read_content": mock_read,
            "message_id": "msg_svg",
        }

        mock_file = MagicMock()
        mock_file.id = "svg_file_id"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert "inline=false" in artifact["preview_url"]

    @pytest.mark.asyncio
    async def test_plain_text_allows_inline(self) -> None:
        """纯文本文件 preview_url 应允许 inline"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"Hello World"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "note.txt", "path": "/workspace/note.txt", "type": "document"}],
            "read_content": mock_read,
            "message_id": "msg_txt",
        }

        mock_file = MagicMock()
        mock_file.id = "txt_file_id"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert "inline=false" not in artifact["preview_url"]


class TestArtifactProcessorLargeFile:
    """测试大文件跳过逻辑"""

    @pytest.mark.asyncio
    async def test_large_file_skipped(self) -> None:
        """超过 5MB 的文件应被跳过"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"x" * (6 * 1024 * 1024)

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "huge.bin", "path": "/workspace/huge.bin", "type": "binary"}],
            "read_content": mock_read,
            "message_id": "msg_big",
        }

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            result = await processor.process_artifacts_ready(event)

        assert result is None
        mock_save.assert_not_called()


class TestLocalArtifactProcessor:
    """测试 LocalArtifactProcessor（本地模式）"""

    @pytest.mark.asyncio
    async def test_local_processor_saves_reference(self) -> None:
        """本地模式应保存路径引用而非文件内容"""
        from app.core.artifacts import LocalArtifactProcessor

        processor = LocalArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"file content"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "output.py", "path": "/workspace/output.py", "type": "code"}],
            "read_content": mock_read,
            "message_id": "msg_local",
        }

        mock_file = MagicMock()
        mock_file.id = "local_file_id"

        with patch("app.core.storage.service.FilesService.save_file_reference", new_callable=AsyncMock) as mock_save_ref:
            mock_save_ref.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        assert result["type"] == "artifacts"
        mock_save_ref.assert_called_once()

        call_kwargs = mock_save_ref.call_args
        assert call_kwargs.kwargs["sandbox_path"] == "/workspace/output.py"

    @pytest.mark.asyncio
    async def test_local_processor_large_file_skipped(self) -> None:
        """本地模式下大文件同样应被跳过"""
        from app.core.artifacts import LocalArtifactProcessor

        processor = LocalArtifactProcessor(chat_id="c1", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"x" * (6 * 1024 * 1024)

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "huge.bin", "path": "/workspace/huge.bin", "type": "binary"}],
            "read_content": mock_read,
            "message_id": "msg_big_local",
        }

        with patch("app.core.storage.service.FilesService.save_file_reference", new_callable=AsyncMock) as mock_save_ref:
            result = await processor.process_artifacts_ready(event)

        assert result is None
        mock_save_ref.assert_not_called()

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


class TestSpreadsheetArtifactIntegration:
    """Spreadsheet artifact 全链路集成测试：harness 类型推断 → processor → 前端事件"""

    @pytest.mark.asyncio
    async def test_csv_artifact_type_flows_to_frontend_event(self) -> None:
        """CSV 文件经过 ArtifactProcessor 后，前端收到 type=spreadsheet"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="test_csv", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"name,age,city\nAlice,30,NYC\nBob,25,LA"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "data.csv", "path": "/workspace/data.csv", "type": "document"}],
            "read_content": mock_read,
            "message_id": "msg_csv",
        }

        mock_file = MagicMock()
        mock_file.id = "csv_file_id"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert artifact["filename"] == "data.csv"
        assert artifact["type"] == "spreadsheet"

    @pytest.mark.asyncio
    async def test_tsv_artifact_type_flows_to_frontend_event(self) -> None:
        """TSV 文件经过 ArtifactProcessor 后，前端收到 type=spreadsheet"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="test_tsv", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"name\tage\tcity\nAlice\t30\tNYC"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "data.tsv", "path": "/workspace/data.tsv", "type": "document"}],
            "read_content": mock_read,
            "message_id": "msg_tsv",
        }

        mock_file = MagicMock()
        mock_file.id = "tsv_file_id"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert artifact["type"] == "spreadsheet"

    @pytest.mark.asyncio
    async def test_xlsx_artifact_type_flows_to_frontend_event(self) -> None:
        """XLSX 文件经过 ArtifactProcessor 后，前端收到 type=spreadsheet"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="test_xlsx", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"PK\x03\x04fake-xlsx-content"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "report.xlsx", "path": "/workspace/report.xlsx", "type": "binary"}],
            "read_content": mock_read,
            "message_id": "msg_xlsx",
        }

        mock_file = MagicMock()
        mock_file.id = "xlsx_file_id"

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert artifact["type"] == "spreadsheet"
        assert "preview_url" in artifact
        assert "download_url" in artifact

    @pytest.mark.asyncio
    async def test_mixed_artifacts_types_correct(self) -> None:
        """混合文件类型时，各自的 type 均正确"""
        from app.core.artifacts import ArtifactProcessor

        processor = ArtifactProcessor(chat_id="test_mix", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"content"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [
                {"filename": "data.csv", "path": "/workspace/data.csv", "type": "document"},
                {"filename": "script.py", "path": "/workspace/script.py", "type": "code"},
                {"filename": "image.png", "path": "/workspace/image.png", "type": "image"},
            ],
            "read_content": mock_read,
            "message_id": "msg_mix",
        }

        file_counter = 0

        async def mock_save(filename: str, content: bytes, content_type: str, source_chat_id: str) -> MagicMock:
            nonlocal file_counter
            file_counter += 1
            mock_file = MagicMock()
            mock_file.id = f"file_{file_counter}"
            return mock_file

        with patch("app.core.storage.service.FilesService.save_generated_file", new_callable=AsyncMock) as save_mock:
            save_mock.side_effect = mock_save
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        data = result["data"]
        assert len(data) == 3

        types_by_name = {a["filename"]: a["type"] for a in data}
        assert types_by_name["data.csv"] == "spreadsheet"
        assert types_by_name["script.py"] == "code"
        assert types_by_name["image.png"] == "image"


class TestLocalSpreadsheetArtifactIntegration:
    """本地模式下 spreadsheet artifact 全链路集成测试"""

    @pytest.mark.asyncio
    async def test_local_csv_artifact_type(self) -> None:
        """本地模式下 CSV 文件也能正确推断为 spreadsheet"""
        from app.core.artifacts import LocalArtifactProcessor

        processor = LocalArtifactProcessor(chat_id="test_local_csv", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"id,name\n1,Alice"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "local.csv", "path": "/workspace/local.csv", "type": "document"}],
            "read_content": mock_read,
            "message_id": "msg_local_csv",
        }

        mock_file = MagicMock()
        mock_file.id = "local_csv_id"

        with patch("app.core.storage.service.FilesService.save_file_reference", new_callable=AsyncMock) as mock_save_ref:
            mock_save_ref.return_value = mock_file
            result = await processor.process_artifacts_ready(event)

        assert result is not None
        artifact = result["data"][0]
        assert artifact["type"] == "spreadsheet"
        assert artifact["filename"] == "local.csv"

    @pytest.mark.asyncio
    async def test_local_xls_artifact_type(self) -> None:
        """本地模式下 .xls 文件正确推断为 spreadsheet"""
        from app.core.artifacts import LocalArtifactProcessor

        processor = LocalArtifactProcessor(chat_id="test_local_xls", api_prefix="/api/v1")

        async def mock_read(path: str) -> bytes:
            return b"\xd0\xcf\x11\xe0fake-xls"

        event: dict[str, object] = {
            "type": "artifacts_ready",
            "data": [{"filename": "legacy.xls", "path": "/workspace/legacy.xls", "type": "binary"}],
            "read_content": mock_read,
            "message_id": "msg_local_xls",
        }

        mock_file = MagicMock()
        mock_file.id = "local_xls_id"

        with patch("app.core.storage.service.FilesService.save_file_reference", new_callable=AsyncMock) as mock_save_ref:
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
