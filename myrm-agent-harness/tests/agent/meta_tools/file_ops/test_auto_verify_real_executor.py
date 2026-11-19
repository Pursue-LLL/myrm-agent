"""Auto-Verify through the real file tools and a real local executor.

The linter is a stand-in ``pyright`` script on PATH that records the directory it ran in (a file in that directory,
which is where the executor's sandbox lets a command write) and reports one error, so no type checker has to be
installed while the real shell, the real ``which`` probe, the real executor and the real file tools all run.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.file_edit_tool import create_file_edit_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.agent.meta_tools.file_ops.validators.auto_verify import _reset_cache
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in linter is a POSIX shell script")

# Called as ``pyright --outputjson <path>``: leave ``ran_in.txt`` in the directory it ran in, then report one error.
_STAND_IN_LINTER = """#!/bin/sh
pwd > ran_in.txt
printf '{"generalDiagnostics": [{"file": "%s", "severity": "error", "message": "Type mismatch", "range": {"start": {"line": 0, "character": 0}}}]}\\n' "$2"
exit 1
"""


@pytest.fixture(autouse=True)
def _fresh_linter_probe() -> Iterator[None]:
    _reset_cache()
    yield
    _reset_cache()


@pytest.fixture
def linter_on_path(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path_factory.mktemp("linter")
    linter = bin_dir / "pyright"
    linter.write_text(_STAND_IN_LINTER, encoding="utf-8")
    linter.chmod(linter.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linter_on_path: None) -> Iterator[LocalExecutor]:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(WorkspacePathResolver, "_cached_workspace_root", None)
    local = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))
    token = set_executor(local)
    yield local
    reset_executor(token)


@pytest.fixture(autouse=True)
async def _close_shells(executor: LocalExecutor) -> AsyncIterator[None]:
    yield
    await executor.close()


@pytest.fixture
def workspace(tmp_path: Path, executor: LocalExecutor) -> Path:
    return tmp_path


async def _write(path: str, content: str) -> str:
    result = await create_file_write_tool().ainvoke({"path": path, "content": content}, config=RunnableConfig())
    assert isinstance(result, str)
    return result


async def _edit(path: str, old: str, new: str) -> str:
    result = await create_file_edit_tool().ainvoke(
        {"path": path, "edits": [{"old_str": old, "new_str": new}]}, config=RunnableConfig()
    )
    assert isinstance(result, str)
    return result


async def test_a_python_write_gets_the_linter_report_and_the_linter_runs_from_the_workspace_root(
    workspace: Path, executor: LocalExecutor
) -> None:
    (workspace / "pkg").mkdir()
    # An earlier bash call of the model left the persistent shell in a subdirectory.
    await executor.execute_bash(ExecutionContext(code="cd pkg", workspace_root=str(workspace)))

    # Code ``ruff format`` leaves as it is: the file keeps its content whether or not the formatter is on PATH.
    result = await _write("pkg/mod.py", 'x: int = "a"\n')

    assert "Successfully created" in result
    assert "[Auto-Verify]" in result
    assert "Type mismatch" in result
    assert (workspace / "pkg" / "mod.py").read_text(encoding="utf-8") == 'x: int = "a"\n'
    ran_in = Path((workspace / "ran_in.txt").read_text(encoding="utf-8").strip())
    assert ran_in.resolve() == workspace.resolve()


async def test_a_python_edit_gets_the_linter_report_and_keeps_the_edit(workspace: Path) -> None:
    await _write("mod.py", "x = 1\n")

    result = await _edit("mod.py", "x = 1", "x = 2")

    assert "Successfully replaced text" in result
    assert "[Auto-Verify]" in result
    assert (workspace / "mod.py").read_text(encoding="utf-8") == "x = 2\n"


async def test_a_file_in_a_language_without_a_registered_linter_starts_no_linter(workspace: Path) -> None:
    result = await _write("app.ts", "const a: number = 'x';\n")

    assert "Successfully created" in result
    assert "[Auto-Verify]" not in result
    assert not (workspace / "ran_in.txt").exists()
