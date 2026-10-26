"""Integration tests for file_read_tool vault reads without mocking vault resolution."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.sub_agents.executor_helpers import _auto_vault_or_truncate
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

_DUMMY_CONFIG = RunnableConfig()


def _reset_workspace_cache() -> None:
    WorkspacePathResolver._cached_workspace_root = None


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    ws = str(tmp_path)
    _reset_workspace_cache()
    os.environ["WORKSPACE_ROOT"] = ws
    yield ws
    os.environ.pop("WORKSPACE_ROOT", None)
    _reset_workspace_cache()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_file_read_tool_reads_auto_vaulted_subagent_result(workspace: str) -> None:
    config = SubagentConfig(system_prompt="t", auto_vault_threshold=80, max_result_tokens=40)
    payload = "CHAIN_" + ("z" * 200)
    summary = _auto_vault_or_truncate(payload, config, {"workspace_path": workspace}, "int-read", "coder")
    match = re.search(r"vault://[a-f0-9-]+", summary)
    assert match is not None

    executor = LocalExecutor(ExecutionConfig(), workspace_path=workspace)
    token = set_executor(executor)
    try:
        tool = create_file_read_tool()
        result = await tool.ainvoke({"paths": [match.group(0)], "mode": "all"}, config=_DUMMY_CONFIG)
    finally:
        reset_executor(token)

    assert isinstance(result, str)
    assert payload in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_file_read_tool_reads_vault_when_process_cwd_is_not_the_chat_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run bound to a chat workspace reads what it spilled, wherever the process was started."""
    chat_ws = tmp_path / "chat_ws"
    chat_ws.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
    _reset_workspace_cache()

    payload = "SPILLED_" + ("q" * 200)
    uri = ArtifactVault(str(chat_ws)).put(payload, "spill.txt")

    executor = LocalExecutor(ExecutionConfig(), workspace_path=str(chat_ws))
    executor_token = set_executor(executor)
    root_token = workspace_root_var.set(str(chat_ws))
    try:
        tool = create_file_read_tool()
        result = await tool.ainvoke({"paths": [uri], "mode": "all"}, config=_DUMMY_CONFIG)
    finally:
        workspace_root_var.reset(root_token)
        reset_executor(executor_token)
        _reset_workspace_cache()

    assert isinstance(result, str)
    assert payload in result
