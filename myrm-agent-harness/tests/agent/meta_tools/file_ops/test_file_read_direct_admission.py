"""``preview`` and ``stream`` open files themselves, so they answer to the same gates as ``all``.

The file service refuses traversal, symlinks, dangerous roots and paths outside a sub-agent's capability
scope, but ``preview`` and ``stream`` skipped it: the same path that ``all`` refused came back with its
contents. These tests send real reads through ``file_read_tool`` with a real ``LocalExecutor``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read import text_paths
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.sub_agents.spawn_capability import derive_spawn_capability
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.core.security.ocap import capability_scope
from myrm_agent_harness.core.security.path import filesystem
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

_DIRECT_MODES = ["preview", "stream"]


@dataclass(frozen=True)
class World:
    workspace: Path
    outside: Path
    ssh_key: Path


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    root = tmp_path.resolve()
    workspace = root / "ws"
    outside = root / "outside"
    ssh_dir = root / "home" / ".ssh"
    for directory in (workspace / "src", workspace / "real", outside, ssh_dir):
        directory.mkdir(parents=True)
    (workspace / "src" / "a.py").write_text("INSIDE-CONTENT\n", encoding="utf-8")
    (workspace / "real" / "r.txt").write_text("LINKED-INSIDE-CONTENT\n", encoding="utf-8")
    (outside / "plain.txt").write_text("OUTSIDE-CONTENT\n", encoding="utf-8")
    (ssh_dir / "id_rsa").write_text("PRIVATE-KEY-CONTENT\n", encoding="utf-8")
    os.symlink(outside, workspace / "link_out")
    os.symlink(workspace / "real", workspace / "link_in")
    monkeypatch.setattr(filesystem, "DANGEROUS_PATHS", frozenset({str(ssh_dir)}))

    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(workspace)))
    workspace_token = workspace_root_var.set(str(workspace))
    yield World(workspace=workspace, outside=outside, ssh_key=ssh_dir / "id_rsa")
    workspace_root_var.reset(workspace_token)
    reset_executor(executor_token)


async def _read(path: str, mode: str) -> str:
    tool = create_file_read_tool()
    return str(await tool.ainvoke({"paths": [path], "mode": mode}, config=RunnableConfig()))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _DIRECT_MODES)
async def test_a_file_in_the_workspace_is_still_read_directly(world: World, mode: str) -> None:
    text = await _read("src/a.py", mode)

    assert "INSIDE-CONTENT" in text
    assert text.startswith("=== src/a.py")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _DIRECT_MODES)
async def test_a_file_outside_the_workspace_that_the_user_may_open_is_still_read_directly(
    world: World, mode: str
) -> None:
    text = await _read(str(world.outside / "plain.txt"), mode)

    assert "OUTSIDE-CONTENT" in text
    assert text.startswith("=== ")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _DIRECT_MODES)
@pytest.mark.parametrize(
    ("target", "secret"),
    [
        ("../outside/plain.txt", "OUTSIDE-CONTENT"),
        ("link_out/plain.txt", "OUTSIDE-CONTENT"),
        ("{ssh_key}", "PRIVATE-KEY-CONTENT"),
    ],
    ids=["traversal", "symlink-out-of-the-workspace", "dangerous-root"],
)
async def test_a_path_the_file_service_refuses_is_refused_in_every_mode(
    world: World, mode: str, target: str, secret: str
) -> None:
    path = target.format(ssh_key=world.ssh_key)

    refused = await _read(path, "all")
    answered = await _read(path, mode)

    assert secret not in refused
    assert secret not in answered
    assert answered == refused


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _DIRECT_MODES)
async def test_a_symlink_that_stays_inside_the_workspace_is_still_readable(world: World, mode: str) -> None:
    text = await _read("link_in/r.txt", mode)

    assert "LINKED-INSIDE-CONTENT" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _DIRECT_MODES)
async def test_a_refusal_is_a_warning_from_the_gate_and_not_a_crash_trace(
    world: World, mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        await _read("../outside/plain.txt", mode)

    from_the_tool = [r for r in caplog.records if r.name == text_paths.__name__]
    assert [r.levelno for r in from_the_tool] == [logging.WARNING]
    assert from_the_tool[0].exc_info is None


def _scoped_to_workspace(workspace: Path):
    handle = derive_spawn_capability(
        parent_agent=SimpleNamespace(_last_context={"workspace_path": str(workspace)}),
        agent_type="worker",
        readonly=True,
    )
    return capability_scope(handle)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _DIRECT_MODES)
async def test_a_sub_agent_cannot_read_outside_its_capability_scope_in_any_mode(world: World, mode: str) -> None:
    outside = str(world.outside / "plain.txt")

    with _scoped_to_workspace(world.workspace):
        refused = await _read(outside, "all")
        answered = await _read(outside, mode)
        inside = await _read("src/a.py", mode)

    assert "OUTSIDE-CONTENT" not in refused
    assert answered == refused
    assert "INSIDE-CONTENT" in inside


class _UnboundExecutor:
    @property
    def workspace_path(self) -> str:
        raise RuntimeError("Workspace not bound. Call bind_workspace() first.")


@pytest.mark.asyncio
async def test_nothing_is_opened_directly_without_a_bound_workspace() -> None:
    executor = cast("CodeExecutor", _UnboundExecutor())

    assert not await text_paths._direct_read_admitted(Path("/data/a.txt"), executor, None, None)
