"""``resolve_path`` is the sandbox boundary every file operation passes through.

These tests drive the real ``LocalExecutor``: the ``/workspace`` alias maps onto the bound workspace by
whole path segments, and everything that resolves outside the workspace is refused.
"""

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


@pytest.fixture
def executor(workspace: Path) -> LocalExecutor:
    ex = LocalExecutor(ExecutionConfig())
    ex.bind_workspace(str(workspace))
    return ex


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "expected_tail"),
    [
        ("/workspace", ""),
        ("/workspace/src/app.py", "src/app.py"),
        ("/workspace//src/app.py", "src/app.py"),
        ("src/app.py", "src/app.py"),
    ],
)
async def test_container_alias_maps_onto_workspace(executor, workspace, raw, expected_tail):
    assert await executor.resolve_path(raw) == str((workspace.resolve() / expected_tail).resolve())


@pytest.mark.asyncio
async def test_lookalike_of_container_alias_is_not_stripped(executor, workspace):
    # ``/workspace2/x`` is a different absolute directory, not ``<workspace>/2/x``.
    with pytest.raises(ValueError, match="Path traversal detected"):
        await executor.resolve_path("/workspace2/x.txt")


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["../outside.txt", "/etc/hosts", "/workspace/../outside.txt"])
async def test_paths_outside_workspace_are_refused(executor, raw):
    with pytest.raises(ValueError, match="Path traversal detected"):
        await executor.resolve_path(raw)
