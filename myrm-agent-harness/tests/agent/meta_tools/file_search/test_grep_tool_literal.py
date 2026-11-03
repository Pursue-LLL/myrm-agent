"""Tests for grep_tool literal mode: ``literal=True`` matches the text exactly instead of as a regex."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_search.grep_tool import (
    create_grep_tool,
)
from myrm_agent_harness.utils.errors import ToolError

# ---------------------------------------------------------------------------
# Literal mode tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGrepLiteralMode:
    """Tests for literal=True exact text matching."""

    async def test_literal_matches_special_chars_exactly(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """literal=True matches regex special characters as-is."""
        (workspace / "api.py").write_text('result = response.json()\ndata = result["key"]\n')
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "response.json()", "literal": True},
                config=runnable_config,
            )
            assert "response.json()" in result
            assert "api.py" in result

    async def test_literal_does_not_regex_match(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """literal=True with '.' should NOT match arbitrary characters."""
        (workspace / "test_lit.py").write_text("responseXjson_call\nresponse.json()\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "response.json()", "literal": True},
                config=runnable_config,
            )
            assert "response.json()" in result
            assert "responseXjson" not in result

    async def test_literal_ignore_case(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """literal=True respects ignore_case."""
        (workspace / "mixed.txt").write_text("Response.JSON()\nresponse.json()\nNOTHING\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "response.json()", "literal": True, "ignore_case": True},
                config=runnable_config,
            )
            assert "Response.JSON()" in result
            assert "response.json()" in result
            assert "NOTHING" not in result

    async def test_literal_empty_pattern_raises(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """literal=True with empty pattern raises ToolError."""
        tool_fn = create_grep_tool()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
                return_value=mock_executor,
            ),
            pytest.raises(ToolError),
        ):
            await tool_fn.ainvoke(
                {"pattern": "", "literal": True},
                config=runnable_config,
            )

    async def test_literal_default_false_preserves_regex(
        self, workspace: Path, mock_executor: MagicMock, runnable_config: RunnableConfig
    ) -> None:
        """Default literal=False preserves existing regex behavior."""
        (workspace / "regex_test.py").write_text("def hello():\ndef world():\nclass Foo:\n")
        tool_fn = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=mock_executor,
        ):
            result = await tool_fn.ainvoke(
                {"pattern": "def \\w+\\("},
                config=runnable_config,
            )
            assert "hello" in result
            assert "world" in result
