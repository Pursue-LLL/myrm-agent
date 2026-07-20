"""Integration test: auto-vault → file_read_tool → vault content API (no vault mocks)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableConfig
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.sub_agents.executor_helpers import _auto_vault_or_truncate
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver


def _reset_workspace_cache() -> None:
    WorkspacePathResolver._cached_workspace_root = None


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> str:
    ws = str(tmp_path)
    _reset_workspace_cache()
    os.environ["WORKSPACE_ROOT"] = ws
    yield ws
    os.environ.pop("WORKSPACE_ROOT", None)
    _reset_workspace_cache()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auto_vault_file_read_and_api_content(
    client: TestClient,
    tmp_workspace: str,
) -> None:
    """Subagent auto-vault, parent file_read_tool recovery, and HTTP content API."""
    from app.api.dependencies import get_workspace_root

    client.app.dependency_overrides[get_workspace_root] = lambda: Path(tmp_workspace)

    config = SubagentConfig(
        system_prompt="integration",
        auto_vault_threshold=100,
        max_result_tokens=80,
    )
    full_payload = "INTEGRATION_MARKER_" + ("payload-" * 200)
    summary = _auto_vault_or_truncate(
        full_payload,
        config,
        {"workspace_path": tmp_workspace},
        "integration-task",
        "coder",
    )

    match = re.search(r"vault://[a-f0-9-]+", summary)
    assert match is not None, summary
    pointer = match.group(0)
    assert "file_read_tool" in summary

    executor = LocalExecutor(ExecutionConfig(), workspace_path=tmp_workspace)
    token = set_executor(executor)
    try:
        tool = create_file_read_tool()
        read_result = await tool.ainvoke({"paths": [pointer], "mode": "all"}, config=RunnableConfig())
    finally:
        reset_executor(token)

    assert isinstance(read_result, str)
    assert "INTEGRATION_MARKER_" in read_result
    assert full_payload in read_result

    obj_id = pointer.removeprefix("vault://").split(":")[0]
    meta_res = client.get(f"/api/v1/files/vault/{obj_id}/meta")
    assert meta_res.status_code == 200
    assert meta_res.json()["filename"] == "subagent_integration-task.md"

    content_res = client.get(f"/api/v1/files/vault/{obj_id}/content")
    assert content_res.status_code == 200
    assert content_res.text == full_payload


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auto_vault_isolated_parent_workspace_api(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """ISOLATED_COPY: vault in parent workspace is readable via API and file_read_tool."""
    from app.api.dependencies import get_workspace_root

    parent_ws = tmp_path / "parent"
    child_ws = tmp_path / "child"
    parent_ws.mkdir()
    child_ws.mkdir()
    _reset_workspace_cache()
    os.environ["WORKSPACE_ROOT"] = str(parent_ws)

    client.app.dependency_overrides[get_workspace_root] = lambda: parent_ws

    config = SubagentConfig(system_prompt="iso", auto_vault_threshold=50, max_result_tokens=40)
    payload = "ISOLATED_" + ("z" * 120)
    summary = _auto_vault_or_truncate(
        payload,
        config,
        {
            "workspace_path": str(child_ws),
            "_isolated_parent_workspace": str(parent_ws),
        },
        "iso-task",
        "coder",
    )
    match = re.search(r"vault://[a-f0-9-]+", summary)
    assert match is not None
    pointer = match.group(0)

    executor = LocalExecutor(ExecutionConfig(), workspace_path=str(parent_ws))
    token = set_executor(executor)
    try:
        tool = create_file_read_tool()
        read_result = await tool.ainvoke({"paths": [f"{pointer}:1-5"], "mode": "all"}, config=RunnableConfig())
    finally:
        reset_executor(token)

    assert isinstance(read_result, str)
    assert "ISOLATED_" in read_result

    obj_id = pointer.removeprefix("vault://")
    content_res = client.get(f"/api/v1/files/vault/{obj_id}/content")
    assert content_res.status_code == 200
    assert content_res.text == payload

    os.environ.pop("WORKSPACE_ROOT", None)
    _reset_workspace_cache()
