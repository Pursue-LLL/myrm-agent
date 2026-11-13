"""Tests for glob_tool — file name search tool.

Covers:
- Factory creation and tool metadata
- Basic glob matching (*, **, extensions)
- Path validation and error handling
- Result limit enforcement
- Empty result handling
- Sorted output
- Nested directory search
- Invalid pattern handling
- Python-tier selection under git's ignore rules and under the ignore files of a plain folder
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import FileIOConfig
from myrm_agent_harness.agent.meta_tools.file_search.glob_tool import (
    GlobInput,
    create_glob_tool,
)
from myrm_agent_harness.utils.errors import ToolError
from tests.agent.meta_tools.file_search.search_probe import SearchRunner, git, write_tree

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with test files."""
    (tmp_path / "main.py").write_text("print('main')\n")
    (tmp_path / "utils.py").write_text("def util(): pass\n")
    (tmp_path / "config.json").write_text("{}\n")
    (tmp_path / "README.md").write_text("# Hello\n")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "app.py").write_text("app = True\n")
    (sub / "test_app.py").write_text("def test(): pass\n")
    deep = sub / "inner"
    deep.mkdir()
    (deep / "deep.py").write_text("x = 1\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: GlobInput schema
# ---------------------------------------------------------------------------


class TestGlobInput:
    def test_defaults(self) -> None:
        inp = GlobInput(pattern="*.py")
        assert inp.path == "."

    def test_custom_values(self) -> None:
        inp = GlobInput(pattern="**/*.js", path="src")
        assert inp.pattern == "**/*.js"
        assert inp.path == "src"


# ---------------------------------------------------------------------------
# Tests: create_glob_tool
# ---------------------------------------------------------------------------


class TestCreateGlobTool:
    def test_factory_creates_tool(self) -> None:
        tool_fn = create_glob_tool()
        assert tool_fn.name == "glob_tool"
        assert "Search for matching files" in tool_fn.description
        tool_zh = create_glob_tool(locale="zh-CN")
        assert "搜索匹配的文件" in tool_zh.description

    def test_custom_config(self) -> None:
        cfg = FileIOConfig(max_search_results=5)
        tool_fn = create_glob_tool(cfg)
        assert "5" in tool_fn.description

    async def test_find_python_files(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "*.py"}, config=runnable_config)
            assert "main.py" in result
            assert "utils.py" in result

    async def test_recursive_search(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "**/*.py"}, config=runnable_config)
            assert "deep.py" in result
            assert "app.py" in result

    async def test_test_file_pattern(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "**/test_*.py"}, config=runnable_config)
            assert "test_app.py" in result
            assert "main.py" not in result

    async def test_no_matches(self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "*.xyz"}, config=runnable_config)
            assert "No files found" in result

    async def test_path_not_found(self, mock_executor: MagicMock, runnable_config: RunnableConfig) -> None:
        tool_fn = create_glob_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
                return_value=mock_executor,
            ),
            pytest.raises(ToolError, match="Path not found"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "*.py", "path": "nonexistent"},
                config=runnable_config,
            )

    async def test_not_a_directory(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
                return_value=mock_executor,
            ),
            pytest.raises(ToolError, match="Not a directory"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "*.py", "path": "main.py"},
                config=runnable_config,
            )

    async def test_invalid_path_traversal(self, runnable_config: RunnableConfig) -> None:
        mock_exec = AsyncMock()
        mock_exec.resolve_path = AsyncMock(side_effect=ValueError("path traversal"))
        tool_fn = create_glob_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
                return_value=mock_exec,
            ),
            pytest.raises(ToolError, match="Invalid path"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "*.py", "path": "../../etc"},
                config=runnable_config,
            )

    @pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/mcp/mcp_k8s_ops_skill"])
    async def test_mcp_namespace_gets_guidance_not_a_workspace_error(
        self, path: str, runnable_config: RunnableConfig
    ) -> None:
        mock_exec = AsyncMock()
        mock_exec.resolve_path = AsyncMock(side_effect=ValueError("Path traversal detected (workspace is /private/x)"))
        tool_fn = create_glob_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
                return_value=mock_exec,
            ),
            pytest.raises(ToolError, match="file_read_tool") as exc_info,
        ):
            await tool_fn.ainvoke({"pattern": "*.md", "path": path}, config=runnable_config)

        assert "workspace is" not in str(exc_info.value)
        mock_exec.resolve_path.assert_not_called()

    async def test_result_limit(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        cfg = FileIOConfig(max_search_results=2)
        tool_fn = create_glob_tool(cfg)
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "**/*.py"}, config=runnable_config)
            assert result.endswith("\n... (limited to first 2 results)")

    async def test_output_sorted(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "*.py"}, config=runnable_config)
            lines = [
                line.strip() for line in result.strip().split("\n") if line.strip() and not line.startswith("Found")
            ]
            assert lines == sorted(lines)

    async def test_search_subdirectory(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "*.py", "path": "src"}, config=runnable_config)
            assert "app.py" in result
            assert "main.py" not in result

    async def test_found_count_message(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "*.py"}, config=runnable_config)
            assert "Found" in result
            assert "file(s)" in result

    async def test_unexpected_error_becomes_tool_error(self, runnable_config: RunnableConfig) -> None:
        mock_exec = AsyncMock()
        mock_exec.resolve_path = AsyncMock(side_effect=RuntimeError("unexpected boom"))
        tool_fn = create_glob_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
                return_value=mock_exec,
            ),
            pytest.raises(ToolError, match=r"[Uu]nexpected"),
        ):
            await tool_fn.ainvoke(
                {"pattern": "*.py"},
                config=runnable_config,
            )

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
        tool_fn = create_glob_tool(cfg)
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            await tool_fn.ainvoke({"pattern": "*.py"}, config=runnable_config)
            audit_msgs = [r.message for r in caplog.records if "SECURITY AUDIT" in r.message]
            assert len(audit_msgs) >= 1
            assert "glob_tool" in audit_msgs[0]

    async def test_json_config_files(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        tool_fn = create_glob_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.glob_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke({"pattern": "*.json"}, config=runnable_config)
            assert "config.json" in result

    @pytest.mark.parametrize("engine", ["python"], indirect=True)
    async def test_fallback_respects_gitignore_when_include_ignored_false(
        self, tmp_path: Path, run_glob: SearchRunner, require_git: None
    ) -> None:
        git(tmp_path, "init", "-q")
        write_tree(
            tmp_path,
            {
                ".gitignore": "ignored_dir/\nignored.txt\n",
                "ignored.txt": "ignored\n",
                "visible.txt": "visible\n",
                "ignored_dir/nested.txt": "ignored nested\n",
            },
        )

        result = await run_glob(tmp_path, "**/*.txt", include_ignored=False)

        assert "visible.txt" in result
        assert "ignored.txt" not in result
        assert "ignored_dir" not in result

    @pytest.mark.parametrize("engine", ["python"], indirect=True)
    async def test_fallback_includes_gitignored_when_include_ignored_true(
        self, tmp_path: Path, run_glob: SearchRunner, require_git: None
    ) -> None:
        git(tmp_path, "init", "-q")
        write_tree(tmp_path, {".gitignore": "ignored_only.txt\n", "ignored_only.txt": "ignored\n"})

        result = await run_glob(tmp_path, "**/*.txt", include_ignored=True)

        assert "ignored_only.txt" in result

    @pytest.mark.parametrize("engine", ["python"], indirect=True)
    async def test_fallback_respects_root_ignore_files_without_git_repo(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(
            plain_dir,
            {
                ".gitignore": "ignored_non_git.txt\nignored_non_git_dir/\n",
                "ignored_non_git.txt": "ignored\n",
                "visible_non_git.txt": "visible\n",
                "ignored_non_git_dir/nested.txt": "ignored nested\n",
            },
        )

        result = await run_glob(plain_dir, "**/*.txt", include_ignored=False)

        assert "visible_non_git.txt" in result
        assert "ignored_non_git.txt" not in result
        assert "ignored_non_git_dir" not in result

    @pytest.mark.parametrize("engine", ["python"], indirect=True)
    async def test_fallback_includes_root_ignored_files_when_enabled(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(plain_dir, {".gitignore": "root_ignored.txt\n", "root_ignored.txt": "ignored\n"})

        result = await run_glob(plain_dir, "**/*.txt", include_ignored=True)

        assert "root_ignored.txt" in result
