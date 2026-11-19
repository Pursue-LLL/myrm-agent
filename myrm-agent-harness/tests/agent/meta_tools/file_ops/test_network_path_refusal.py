"""Every gate a tool call's path passes through refuses a network share or NT-namespace path before opening it.

On Windows, opening ``\\\\host\\share\\x`` connects to ``host`` and sends the user's credentials, so a path that a prompt
injection names must not reach ``stat`` or ``resolve`` at all. Each gate is driven with the host flag set to Windows and
a spy on the filesystem calls: a gate that refuses on the text leaves the spy's record empty.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.meta_tools.file_ops.validators.path_validator import PathValidator
from myrm_agent_harness.agent.security.checks import check_path_policy
from myrm_agent_harness.agent.security.session_access import resolve_grant_directory_path
from myrm_agent_harness.agent.security.types import PathPolicy, PermissionAction
from myrm_agent_harness.core.security.path import filesystem as filesystem_module
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.utils.errors import ToolError
from tests.support.network_path_probe import REFUSED_ON_EVERY_HOST, REFUSED_ON_WINDOWS_ONLY, forbid_touching

SPELLINGS = {**REFUSED_ON_EVERY_HOST, **REFUSED_ON_WINDOWS_ONLY}
REFUSED_SPELLING = pytest.mark.parametrize("spelling", SPELLINGS.values(), ids=SPELLINGS.keys())
REFUSAL = "Network share and NT namespace paths"


@pytest.fixture(autouse=True)
def windows_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filesystem_module, "_IS_WINDOWS", True)


@pytest.fixture
def touches(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return forbid_touching(monkeypatch)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


def _context() -> MagicMock:
    context = MagicMock()
    context.operation.value = "create"
    return context


class TestPathValidator:
    @REFUSED_SPELLING
    @pytest.mark.asyncio
    async def test_refuses_before_resolving(self, spelling: str, touches: list[str]) -> None:
        with pytest.raises(PermissionError, match=REFUSAL):
            await PathValidator()._do_validate(_context(), spelling)
        assert touches == []

    @pytest.mark.asyncio
    async def test_a_workspace_file_is_not_refused(self, workspace: Path) -> None:
        await PathValidator()._do_validate(_context(), str(workspace / "src" / "app.py"))


class TestExecutorResolvePath:
    @pytest.fixture
    def executor(self, workspace: Path) -> LocalExecutor:
        bound = LocalExecutor(ExecutionConfig())
        bound.bind_workspace(str(workspace))
        return bound

    @REFUSED_SPELLING
    @pytest.mark.asyncio
    async def test_refuses_before_resolving(self, executor: LocalExecutor, spelling: str, touches: list[str]) -> None:
        with pytest.raises(ValueError, match=REFUSAL):
            await executor.resolve_path(spelling)
        assert touches == []

    @pytest.mark.asyncio
    async def test_a_workspace_file_is_resolved(self, executor: LocalExecutor, workspace: Path) -> None:
        assert await executor.resolve_path("src/app.py") == str((workspace.resolve() / "src" / "app.py").resolve())


class TestFileReadTool:
    @REFUSED_SPELLING
    @pytest.mark.asyncio
    async def test_refuses_before_any_filesystem_call(self, spelling: str, touches: list[str]) -> None:
        tool = create_file_read_tool()
        with pytest.raises(ToolError, match=REFUSAL):
            await tool.ainvoke({"paths": [spelling]}, config={"configurable": {"context": {}}})
        assert touches == []

    @pytest.mark.asyncio
    async def test_a_line_range_does_not_hide_the_spelling(self, touches: list[str]) -> None:
        tool = create_file_read_tool()
        with pytest.raises(ToolError, match=REFUSAL):
            await tool.ainvoke(
                {"paths": [rf"{REFUSED_ON_EVERY_HOST['unc']}:10-20"]}, config={"configurable": {"context": {}}}
            )
        assert touches == []


class TestApprovalPathPolicy:
    @REFUSED_SPELLING
    def test_denies_before_resolving(self, spelling: str, workspace: Path, touches: list[str]) -> None:
        action, reason = check_path_policy(spelling, PathPolicy(), str(workspace))
        assert action is PermissionAction.DENY
        assert REFUSAL in reason
        assert touches == []

    @REFUSED_SPELLING
    def test_a_directory_grant_never_resolves_such_a_path(
        self, spelling: str, workspace: Path, touches: list[str]
    ) -> None:
        assert resolve_grant_directory_path(spelling, str(workspace)) == ""
        assert touches == []

    def test_a_workspace_file_is_not_denied_as_a_network_path(self, workspace: Path) -> None:
        action, reason = check_path_policy("src/app.py", PathPolicy(), str(workspace))
        assert action is PermissionAction.ALLOW
        assert reason == ""
