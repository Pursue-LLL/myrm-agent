"""file_read redacts each file by its type: source files in source mode, every other file in full."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.view_redaction import redact_read_view
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool

_CODE = "total_api_tokens = 0\npassword: str\n"
_LITERAL = 'DEFAULT_PASSWORD = "Xk9$mP2vLq8"\n'
_ASSIGNMENTS = "total_api_tokens = 0\nDB_PASSWORD=hunter2\n"


@pytest.mark.parametrize("path", ["src/a.py", "src/a.PY", "ui/a.tsx", "pkg/main.go", "src/a.py:10-20", "/abs/lib.rs"])
def test_source_files_keep_credential_named_code_readable(path: str) -> None:
    assert redact_read_view(path, _CODE) == _CODE
    assert "Xk9$mP2vLq8" not in redact_read_view(path, _LITERAL)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "config/.env.production",
        "app.yaml",
        "data.json",
        "pyproject.toml",
        "run.sh",
        "notes.md",
        "Makefile",
        "LICENSE",
    ],
)
def test_every_other_file_is_redacted_in_full(path: str) -> None:
    out = redact_read_view(path, _ASSIGNMENTS)
    assert "hunter2" not in out
    assert "total_api_tokens=***" in out


@pytest.mark.asyncio
async def test_the_tool_redacts_each_path_by_its_own_type() -> None:
    texts = [f"=== a.py ===\n{_CODE}{_LITERAL}", f"=== .env ===\n{_ASSIGNMENTS}"]
    tool = create_file_read_tool()
    with (
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool.get_executor",
            return_value=MagicMock(workspace_path="/tmp"),
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool.process_text_paths",
            new_callable=AsyncMock,
            return_value=texts,
        ),
    ):
        out = await tool.ainvoke({"paths": ["a.py", ".env"]}, config=RunnableConfig())

    assert _CODE in out
    assert "Xk9$mP2vLq8" not in out
    assert "hunter2" not in out
    assert "total_api_tokens=***" in out
