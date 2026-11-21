"""``resolve_path`` is the sandbox boundary every file operation passes through.

These tests drive the real ``LocalExecutor``: the ``/workspace`` alias maps onto the bound workspace by
whole path segments, a bare ``~`` is the user's home as the permission engine reads it and no other spelling is
expanded, and everything that resolves outside the workspace is refused.
"""

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.context_vars import scoped_value, session_access_roots_var
from myrm_agent_harness.core.security.path import opened_path
from myrm_agent_harness.core.security.types import AccessRoot
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


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(path))
    return path.resolve()


@pytest.mark.asyncio
async def test_home_spelling_opens_the_file_the_permission_engine_judged(executor, home):
    # The engine reads ``~/notes.txt`` as a file of the user's home; once the user grants the home, that is the file.
    with scoped_value(session_access_roots_var, (AccessRoot(path=str(home), writable=True),)):
        assert await executor.resolve_path("~/notes.txt") == str(home / "notes.txt")
        assert await executor.resolve_path("~") == str(home)


@pytest.mark.asyncio
async def test_home_spelling_is_refused_without_a_grant(executor, home):
    with pytest.raises(ValueError, match="Path traversal detected"):
        await executor.resolve_path("~/notes.txt")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["~$notes.txt", "~backup/notes.txt", "~root/notes.txt"])
async def test_other_tilde_names_stay_workspace_paths(executor, workspace, home, name):
    assert await executor.resolve_path(name) == str((workspace / name).resolve())


@pytest.mark.asyncio
async def test_environment_variable_spelling_stays_a_workspace_path(executor, workspace, monkeypatch):
    # The permission engine reads it the same way, so a link named like a variable is judged as the link it is.
    monkeypatch.setenv("MYRM_UP", "../elsewhere")

    assert await executor.resolve_path("$MYRM_UP/notes.txt") == str((workspace / "$MYRM_UP" / "notes.txt").resolve())


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="links need privileges on Windows")
@pytest.mark.parametrize(
    "typed",
    [
        "/workspace",
        "/workspace/src/app.py",
        "/workspace//src/app.py",
        "/workspace/notes.txt",
        "src/app.py",
        "./src/app.py",
        "src/../src/app.py",
        "notes.txt",
        "notes.txt/",
        "notes.txt//",
        "$MYRM_UP/notes.txt",
        "~backup/notes.txt",
    ],
)
async def test_the_executor_opens_the_file_the_permission_engine_reads(executor, workspace, monkeypatch, typed):
    # What a gate judges and what the tool opens are one file only if both read the typed text the same way.
    monkeypatch.setenv("MYRM_UP", "../elsewhere")
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("print()")
    (workspace / ".env").write_text("CANARY=1")
    (workspace / "notes.txt").symlink_to(".env")

    assert opened_path(typed, str(workspace)) == await executor.resolve_path(typed)
