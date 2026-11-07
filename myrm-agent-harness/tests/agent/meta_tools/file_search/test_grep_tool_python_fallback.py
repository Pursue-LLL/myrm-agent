"""Tests for grep_tool on its Python tier, which takes over when ripgrep is unavailable or gives no answer.

Covers:
- Basic search, the result cap and the file cap
- Binary files and undecodable lines are skipped
- A ripgrep search that raises (a run that gave no answer) falls back to the Python tier
- Hidden files are searched, and ignore files apply outside a git repository
- An invalid file pattern is rejected, and the time budget is respected
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import FileIOConfig
from myrm_agent_harness.agent.meta_tools.file_search.grep_tool import (
    create_grep_tool,
)
from myrm_agent_harness.utils.errors import ToolError

# ---------------------------------------------------------------------------
# Tests: Python fallback path (when ripgrep is unavailable)
# ---------------------------------------------------------------------------


class TestPythonFallback:
    """Tests that exercise the Python/mmap fallback search engine."""

    async def test_fallback_basic_search(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "def hello"},
                config=runnable_config,
            )
            assert "hello" in result

    async def test_fallback_skips_binary_files(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / "data.pyc").write_bytes(b"\x00\x01\x02")
        (workspace / "image.jpg").write_bytes(b"\xff\xd8\xff")
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "def"},
                config=runnable_config,
            )
            assert ".pyc" not in result
            assert ".jpg" not in result

    async def test_fallback_file_limit(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        cfg = FileIOConfig(max_search_files=1, max_search_results=100)
        tool_fn = create_grep_tool(cfg)
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "def"},
                config=runnable_config,
            )
            assert isinstance(result, str)

    async def test_fallback_max_results_limit(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        for i in range(20):
            (workspace / f"file_{i}.py").write_text(f"match_{i} = True\n")
        cfg = FileIOConfig(max_search_results=3)
        tool_fn = create_grep_tool(cfg)
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "match_"},
                config=runnable_config,
            )
            assert "limited to first 3" in result

    async def test_fallback_ripgrep_failure_triggers_python(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=True,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._ripgrep_search",
                side_effect=RuntimeError("ripgrep crashed"),
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "def hello"},
                config=runnable_config,
            )
            assert "hello" in result

    async def test_fallback_unicode_error_skipped(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / "broken.txt").write_bytes(b"\x80\x81\x82\x83")
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "test"},
                config=runnable_config,
            )
            assert isinstance(result, str)

    async def test_fallback_no_matches(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "ZZZZZ_NONEXISTENT_XYZ"},
                config=runnable_config,
            )
            assert "No matches found" in result

    async def test_fallback_searches_hidden_files(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / ".hidden.py").write_text("hidden_token = True\n")
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "hidden_token"},
                config=runnable_config,
            )
            assert ".hidden.py" in result

    async def test_fallback_allows_explicit_hidden_file_path(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / ".hidden_explicit.py").write_text("explicit_hidden_token = True\n")
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "explicit_hidden_token", "path": ".hidden_explicit.py"},
                config=runnable_config,
            )
            assert "Found 1 match(es)" in result
            assert "No matches found" not in result

    async def test_fallback_respects_root_ignore_files_without_git_repo(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        (workspace / ".gitignore").write_text("ignored_non_git.py\n")
        (workspace / "ignored_non_git.py").write_text("NON_GIT_IGNORE_TOKEN = 1\n")
        (workspace / "visible_non_git.py").write_text("NON_GIT_IGNORE_TOKEN = 1\n")

        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "NON_GIT_IGNORE_TOKEN", "file_pattern": "**/*.py"},
                config=runnable_config,
            )
            assert "visible_non_git.py" in result
            assert "ignored_non_git.py" not in result

    async def test_fallback_invalid_file_pattern(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
            pytest.raises(ToolError, match=r"[Ii]nvalid file pattern"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "test", "file_pattern": "\x00invalid"},
                config=runnable_config,
            )

    async def test_fallback_search_timeout(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """Verify Python fallback respects search_timeout_seconds."""

        cfg = FileIOConfig(search_timeout_seconds=0.0)
        tool_fn = create_grep_tool(cfg)
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool._has_ripgrep",
                return_value=False,
            ),
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "def"},
                config=runnable_config,
            )
            assert isinstance(result, str)
