"""Tests for grep_tool end to end: the tool a model calls.

Covers:
- Factory creation and tool metadata
- Path validation and error handling
- ReDoS protection integration
- Result formatting delegation
- Sensitive text redaction
- File pattern filtering
- Unexpected errors surface as ToolError
- Path densification and audit logging through the full chain
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import FileIOConfig
from myrm_agent_harness.agent.meta_tools.file_search.grep_tool import (
    create_grep_tool,
)
from myrm_agent_harness.utils.errors import ToolError

# ---------------------------------------------------------------------------
# Tests: create_grep_tool integration
# ---------------------------------------------------------------------------


class TestCreateGrepTool:
    def test_factory_creates_tool(self) -> None:
        tool_fn = create_grep_tool()
        assert tool_fn.name == "grep_tool"
        assert "Search file contents" in tool_fn.description
        tool_zh = create_grep_tool(locale="zh-CN")
        assert "搜索文件内容" in tool_zh.description

    def test_custom_config(self) -> None:
        cfg = FileIOConfig(max_search_results=10, max_search_files=5)
        tool_fn = create_grep_tool(cfg)
        assert "10" in tool_fn.description

    async def test_path_not_found(self, mock_executor: MagicMock, runnable_config: RunnableConfig) -> None:
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            pytest.raises(ToolError, match="Path not found"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "test", "path": "nonexistent_dir"},
                config=runnable_config,
            )

    async def test_not_a_directory(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        # Since we removed the is_dir() restriction, this test should now pass and return results
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            # The test sets up a file, so we should be able to grep it
            result = await tool_fn.ainvoke(
                {"pattern": "test", "path": "hello.py"},
                config=runnable_config,
            )
            assert isinstance(result, str)

    async def test_basic_search(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "def hello"},
                config=runnable_config,
            )
            assert "hello" in result
            assert "match" in result.lower()

    async def test_ignore_case_search(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / "case_test.txt").write_text("HELLO\nhello\nHeLLo\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "hello", "ignore_case": True},
                config=runnable_config,
            )
            assert "match" in result.lower()

    async def test_cache_hit(self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig) -> None:
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result1 = await tool_fn.ainvoke(
                {"pattern": "def hello"},
                config=runnable_config,
            )
            result2 = await tool_fn.ainvoke(
                {"pattern": "def hello"},
                config=runnable_config,
            )
            assert result1 == result2

    async def test_redact_sensitive_text(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / "secrets.py").write_text('API_KEY = "sk-abc123def456"\n')
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "API_KEY"},
                config=runnable_config,
            )
            assert isinstance(result, str)
            assert "sk-abc123def456" not in result
            assert "***" in result

    async def test_redact_cli_flag_equals_output(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / "cli.sh").write_text("run --api-key=sk-abcdefghijklmnop1234\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "api-key"},
                config=runnable_config,
            )
            assert "sk-abcdefghijklmnop1234" not in result
            assert "sk-abc" in result

    async def test_redact_dotted_key_output(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / "app.conf").write_text("app.api.key=sk-abcdefghijklmnop1234\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "app.api.key"},
                config=runnable_config,
            )
            assert "sk-abcdefghijklmnop1234" not in result
            assert "sk-abc" in result

    async def test_redos_protection(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            pytest.raises(ToolError, match=r"[Dd]angerous|[Nn]ested"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "(a+)+"},
                config=runnable_config,
            )

    async def test_no_matches(self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig) -> None:
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "ZZZZZ_NONEXISTENT"},
                config=runnable_config,
            )
            assert "No matches found" in result

    async def test_file_pattern_filter(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "import", "file_pattern": "**/*.py"},
                config=runnable_config,
            )
            assert "import" in result
            assert ".json" not in result

    async def test_invalid_path(self, mock_executor: MagicMock, runnable_config: RunnableConfig) -> None:
        mock_executor_bad = AsyncMock()
        mock_executor_bad.resolve_path = AsyncMock(side_effect=ValueError("path traversal"))
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor_bad,
            ),
            pytest.raises(ToolError, match="Invalid path"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "test", "path": "../../etc/passwd"},
                config=runnable_config,
            )

    async def test_mcp_namespace_gets_guidance_not_a_workspace_error(self, runnable_config: RunnableConfig) -> None:
        mock_executor_bad = AsyncMock()
        mock_executor_bad.resolve_path = AsyncMock(side_effect=ValueError("Path traversal detected"))
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor_bad,
            ),
            pytest.raises(ToolError, match="file_read_tool"),
        ):
            await tool_fn.ainvoke({"pattern": "pods", "path": "/mcp/mcp_k8s_ops_skill"}, config=runnable_config)

        mock_executor_bad.resolve_path.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Unexpected exception wrapping
# ---------------------------------------------------------------------------


class TestUnexpectedExceptionWrapping:
    async def test_unexpected_error_becomes_tool_error(
        self, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        mock_executor_bad = AsyncMock()
        mock_executor_bad.resolve_path = AsyncMock(side_effect=RuntimeError("unexpected boom"))
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor_bad,
            ),
            pytest.raises(ToolError, match=r"[Uu]nexpected"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "test"},
                config=runnable_config,
            )


# ---------------------------------------------------------------------------
# Tests: Audit log
# ---------------------------------------------------------------------------


class TestAuditLog:
    async def test_densification_triggers_in_full_chain(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """Full-chain integration: grep_tool → ripgrep/mmap → format_grep_results produces densified output."""
        for i in range(6):
            (workspace / f"mod_{i}.py").write_text(f"DENSE_TOKEN = {i}\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "DENSE_TOKEN"},
                config=runnable_config,
            )
            lines = result.split("\n")
            indented = [ln for ln in lines if ln.startswith("  ") and "DENSE_TOKEN" in ln]
            assert len(indented) >= 6, f"Expected densified indented lines, got: {result}"
            path_headers = [ln for ln in lines if ln.strip().endswith(".py") and not ln.startswith("  ")]
            assert len(path_headers) >= 1

    async def test_no_densification_below_threshold(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """Full-chain: grep_tool with < 5 matches stays flat."""
        for i in range(3):
            (workspace / f"small_{i}.py").write_text(f"FLAT_TOKEN = {i}\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "FLAT_TOKEN"},
                config=runnable_config,
            )
            indented = [ln for ln in result.split("\n") if ln.startswith("  ") and "FLAT_TOKEN" in ln]
            assert len(indented) == 0, f"Below threshold should use flat format, got: {result}"

    async def test_audit_log_enabled(
        self,
        workspace: Path,
        mock_executor: MagicMock,
        runnable_config: RunnableConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging

        caplog.set_level(logging.INFO)
        cfg = FileIOConfig(enable_audit_log=True)
        tool_fn = create_grep_tool(cfg)
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            await tool_fn.ainvoke(
                {"pattern": "def"},
                config=runnable_config,
            )
            audit_msgs = [r.message for r in caplog.records if "SECURITY AUDIT" in r.message]
            assert len(audit_msgs) >= 1
            assert "grep_tool" in audit_msgs[0]
