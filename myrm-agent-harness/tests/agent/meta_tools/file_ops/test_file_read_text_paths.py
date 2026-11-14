"""file_read text paths: truncation events, preview and stream modes, MCP and directory paths, the structure outline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths import (
    _dispatch_truncation_event,
    _read_via_service,
    process_text_paths,
)

_DUMMY_CONFIG = RunnableConfig()


@pytest.mark.asyncio
async def test_read_via_service_dispatches_truncation_event() -> None:
    mock_service = MagicMock()
    mock_service.execute = AsyncMock(return_value="long output")
    with (
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths.FileOperationService",
            return_value=mock_service,
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths.truncate_file_output",
            return_value=("short", True, {"tokens": 1}),
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths._dispatch_truncation_event",
            new_callable=AsyncMock,
        ) as mock_dispatch,
    ):
        out = await _read_via_service("f.txt", MagicMock(), None, None, config=_DUMMY_CONFIG)
    assert out == "short"
    mock_dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_truncation_event() -> None:
    with patch(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        new_callable=AsyncMock,
    ) as mock_event:
        await _dispatch_truncation_event({"k": "v"}, tool="file_read", config=_DUMMY_CONFIG)
    mock_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_text_paths_preview_mode(tmp_path: Path) -> None:
    big = tmp_path / "big.txt"
    big.write_text("line\n" * 50, encoding="utf-8")
    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths.read_file_preview",
        new_callable=AsyncMock,
        return_value="preview chunk",
    ):
        parts = await process_text_paths(
            [str(big)],
            mock_executor,
            None,
            None,
            "preview",
            config=_DUMMY_CONFIG,
        )
    assert "preview mode" in parts[0]
    assert "preview chunk" in parts[0]


@pytest.mark.asyncio
async def test_process_text_paths_stream_mode(tmp_path: Path) -> None:
    f = tmp_path / "stream.txt"
    f.write_text("stream data\n", encoding="utf-8")
    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths.read_file_chunked",
        new_callable=AsyncMock,
        return_value="chunked",
    ):
        parts = await process_text_paths(
            [str(f)],
            mock_executor,
            None,
            None,
            "stream",
            config=_DUMMY_CONFIG,
        )
    assert "chunked" in parts[0]


@pytest.mark.asyncio
async def test_process_text_paths_mcp_and_directory(tmp_path: Path) -> None:
    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)
    d = tmp_path / "folder"
    d.mkdir()

    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths._read_via_service",
        new_callable=AsyncMock,
        side_effect=["mcp content", "dir listing"],
    ) as mock_read:
        parts = await process_text_paths(
            ["/mcp/skill/doc.md", str(d)],
            mock_executor,
            None,
            None,
            "all",
            config=_DUMMY_CONFIG,
        )
    assert parts == ["mcp content", "dir listing"]
    assert mock_read.await_count == 2


@pytest.mark.asyncio
async def test_process_text_paths_exception_fallback(tmp_path: Path) -> None:
    f = tmp_path / "broken.txt"
    f.write_text("ok", encoding="utf-8")
    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with (
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths.read_file_preview",
            new_callable=AsyncMock,
            side_effect=OSError("read fail"),
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths._read_via_service",
            new_callable=AsyncMock,
            return_value="fallback content",
        ) as mock_service,
    ):
        parts = await process_text_paths(
            [str(f)],
            mock_executor,
            None,
            None,
            "preview",
            config=_DUMMY_CONFIG,
        )
    mock_service.assert_awaited()
    assert parts[-1] == "fallback content"


@pytest.mark.asyncio
async def test_process_text_paths_structure_mode(tmp_path: Path) -> None:
    """验证 parse_mode='structure' 时结构化提取 Python 代码大纲"""
    py_file = tmp_path / "service.py"
    code = "class OrderService:\n    def create_order(self):\n        pass\n\ndef helper():\n    pass\n"
    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.text_paths._view_text",
        new_callable=AsyncMock,
        return_value=code,
    ):
        parts = await process_text_paths(
            [str(py_file)],
            mock_executor,
            None,
            None,
            "all",
            config=_DUMMY_CONFIG,
            parse_mode="structure",
        )
    assert len(parts) == 1
    assert "[DOCUMENT STRUCTURE OUTLINE: service.py]:" in parts[0]
    assert "class OrderService" in parts[0]
    assert "def OrderService.create_order" in parts[0]
    assert "def helper" in parts[0]
