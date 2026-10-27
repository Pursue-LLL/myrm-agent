"""Fast-track read scope for long pasted text saved by the context guard.

The guard leaves a pointer to ``.myrm/pastes`` (a stored conversation) or ``.myrm/spillover``
(a turn-only spill) in the prompt; the Fast track's ``file_read_tool`` has to follow it, and
nothing else in the workspace may open up with it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, ContextGuardConfig, SpilloverEngine
from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.scope import (
    assert_evicted_uploaded_read_scope,
    path_hint_allowed_for_evicted_uploaded,
)
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver
from myrm_agent_harness.utils.errors import ToolError

_CHAT_ID = "chat-paste"


@pytest.mark.parametrize(
    "path",
    [
        ".myrm/pastes/payload_0123456789abcdef.md",
        "./.myrm/pastes/payload_0123456789abcdef.md",
        ".myrm/spillover/payload_0123456789.md",
        ".myrm/pastes",
    ],
)
def test_the_directories_the_context_guard_writes_are_readable(path: str) -> None:
    assert path_hint_allowed_for_evicted_uploaded(path, _CHAT_ID)


@pytest.mark.parametrize(
    "path",
    [
        ".myrm/pastes-evil/payload.md",
        ".myrm/pastesx",
        ".myrm/pasted/payload.md",
        "myrm/pastes/payload.md",
        "project/.myrm/pastes/payload.md",
        ".myrm/config.json",
        ".myrm/checkpoints/state.sqlite",
    ],
)
def test_a_lookalike_or_neighbouring_directory_stays_closed(path: str) -> None:
    assert not path_hint_allowed_for_evicted_uploaded(path, _CHAT_ID)


@pytest.mark.parametrize(
    "path",
    [
        "_uploaded/../secret.txt",
        ".myrm/pastes/../../secret.txt",
        f".context/{_CHAT_ID}/evicted/../../../secret.txt",
    ],
)
def test_a_parent_segment_is_never_trusted_by_its_prefix(path: str) -> None:
    assert not path_hint_allowed_for_evicted_uploaded(path, _CHAT_ID)


class _Executor:
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    async def resolve_path(self, path: str) -> str:
        return str(self._workspace / path)


@pytest.mark.asyncio
async def test_a_path_that_climbs_out_of_the_scope_is_judged_by_where_it_resolves(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / ".myrm" / "pastes").mkdir(parents=True)
    (workspace / "secret.txt").write_text("source", encoding="utf-8")
    token_ws = workspace_root_var.set(str(workspace))
    try:
        with pytest.raises(ToolError, match="blocked"):
            await assert_evicted_uploaded_read_scope(
                [".myrm/pastes/../../secret.txt"], chat_id=_CHAT_ID, executor=_Executor(workspace)
            )
    finally:
        workspace_root_var.reset(token_ws)


@pytest.mark.asyncio
async def test_the_absolute_path_of_a_pasted_file_is_readable(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    paste = workspace / ".myrm" / "pastes" / "payload_0123456789abcdef.md"
    paste.parent.mkdir(parents=True)
    paste.write_text("pasted", encoding="utf-8")
    token_ws = workspace_root_var.set(str(workspace))
    try:

        class _Absolute(_Executor):
            async def resolve_path(self, path: str) -> str:
                return path

        await assert_evicted_uploaded_read_scope([str(paste)], chat_id=_CHAT_ID, executor=_Absolute(workspace))
    finally:
        workspace_root_var.reset(token_ws)


@pytest.fixture
def workspace(tmp_path: Path):
    ws = str(tmp_path)
    WorkspacePathResolver._cached_workspace_root = None
    os.environ["WORKSPACE_ROOT"] = ws
    yield ws
    os.environ.pop("WORKSPACE_ROOT", None)
    WorkspacePathResolver._cached_workspace_root = None


def _fast_config() -> RunnableConfig:
    return RunnableConfig(configurable={"context": {"chat_id": _CHAT_ID}})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_fast_track_reads_the_pasted_text_back_through_the_real_tool(workspace: str) -> None:
    request = "Which clause disadvantages the supplier?"
    text = "Clause 1.\n" + ("Filler sentence of the agreement.\n" * 40) + request
    spilled = SpilloverEngine(
        ContextGuardConfig(max_message_chars=100, spillover_dir_name=KEPT_SPILLOVER_DIR)
    ).process_content(text, base_dir=workspace)
    assert spilled.payload is not None
    (Path(workspace) / "secret.py").write_text("SECRET = 1\n", encoding="utf-8")
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=workspace))
    chat_token = chat_id_var.set(_CHAT_ID)
    workspace_token = workspace_root_var.set(workspace)
    try:
        tool = create_file_read_tool(path_policy="evicted_uploaded")
        read_back = await tool.ainvoke({"paths": [spilled.payload.relative_path], "mode": "all"}, config=_fast_config())
        with pytest.raises(ToolError, match="blocked"):
            await tool.ainvoke({"paths": ["secret.py"], "mode": "all"}, config=_fast_config())
        with pytest.raises(ToolError, match="blocked"):
            await tool.ainvoke({"paths": ["_uploaded/../secret.py"], "mode": "all"}, config=_fast_config())
    finally:
        workspace_root_var.reset(workspace_token)
        chat_id_var.reset(chat_token)
        reset_executor(executor_token)

    assert isinstance(read_back, str)
    assert request in read_back
    assert "Clause 1." in read_back
