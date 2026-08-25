"""Integration: Fast track UECD read-only file_read mount + real spill reads.

Critical path (resolve_agent_mount → get_meta_tools → file_read_tool on disk via
LocalExecutor) is exercised without mocks. Converter wiring uses real
convert_to_general_agent_params against .env.test model selection.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from myrm_agent_harness.agent.meta_tools import get_meta_tools
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import (
    create_bash_code_execute_tool,
)
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import (
    create_file_read_tool,
)
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import (
    reset_executor,
    set_executor,
)
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import (
    LocalExecutor,
)
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
    WorkspacePathResolver,
)
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import (
    bind_workspace_storage_root,
)
from myrm_agent_harness.utils.errors import ToolError

from app.ai_agents.agents import AgentFactory
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from app.services.agent.profile.profile_resolver import resolve_builtin_tool_flags
from app.services.agent.tool_mount import ExecutionSurface, resolve_agent_mount
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection

_INTEGRATION_MARKER = "UECD_FAST_INTEGRATION_MARKER"


def _reset_workspace_cache() -> None:
    WorkspacePathResolver._cached_workspace_root = None


def _make_local_executor(workspace: Path) -> LocalExecutor:
    from unittest.mock import patch

    from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import (
        NullProvider,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
        SandboxStatus,
    )

    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(workspace))
    null_result = (
        NullProvider(),
        SandboxStatus(enabled=False, provider_name="null", reason="test"),
    )
    patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
        return_value=null_result,
    ).start()
    patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        return_value=null_result,
    ).start()
    return executor


@pytest.fixture(autouse=True)
def _stop_sandbox_patches() -> None:
    yield
    import unittest.mock

    unittest.mock.patch.stopall()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    _reset_workspace_cache()
    os.environ["WORKSPACE_ROOT"] = str(tmp_path)
    bind_workspace_storage_root(tmp_path)
    yield tmp_path
    os.environ.pop("WORKSPACE_ROOT", None)
    _reset_workspace_cache()


@pytest.mark.integration
def test_web_fast_mount_resolves_evicted_read_only_meta_tools() -> None:
    flags = resolve_agent_mount(
        ExecutionSurface.WEB_FAST,
        resolve_builtin_tool_flags(["answer_tool"]),
    )
    assert flags["file_access_mode"] == FileAccessMode.SPILL_AND_UPLOADS
    assert flags["enable_shell_tools"] is False

    registry = ToolRegistry()
    meta_tools = get_meta_tools(
        [],
        skill_backend=None,
        registry=registry,
        file_access_mode=flags["file_access_mode"],
        enable_shell_tools=flags["enable_shell_tools"],
        enable_answer_tool=flags["enable_answer_tool"],
    )
    names = {tool.name for tool in meta_tools}
    assert "file_read_tool" in names
    assert "file_write_tool" not in names
    assert "glob_tool" not in names
    assert "bash_code_execute_tool" not in names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fast_evicted_file_read_reads_real_spill_on_disk(
    workspace: Path,
) -> None:
    chat_id = f"chat-fast-integ-{uuid.uuid4().hex[:8]}"
    filename = f"web_fetch_{uuid.uuid4().hex[:8]}.md"
    evicted_dir = workspace / ".context" / chat_id / "evicted"
    evicted_dir.mkdir(parents=True)
    spill_path = evicted_dir / filename
    spill_path.write_text(
        f"# spill\n\n{_INTEGRATION_MARKER}\n" + ("line\n" * 20),
        encoding="utf-8",
    )
    rel = f".context/{chat_id}/evicted/{filename}"

    executor = _make_local_executor(workspace)
    exec_token = set_executor(executor)
    ws_token = workspace_root_var.set(str(workspace))
    chat_token = chat_id_var.set(chat_id)
    try:
        read_tool = create_file_read_tool(path_policy="evicted_uploaded")
        result = await read_tool.ainvoke(
            {"paths": [rel], "mode": "all"},
            config=RunnableConfig(configurable={"chat_id": chat_id, "supports_vision": False}),
        )
    finally:
        reset_executor(exec_token)
        workspace_root_var.reset(ws_token)
        chat_id_var.reset(chat_token)

    assert isinstance(result, str)
    assert _INTEGRATION_MARKER in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fast_evicted_file_read_blocks_workspace_source_on_disk(
    workspace: Path,
) -> None:
    chat_id = f"chat-fast-block-{uuid.uuid4().hex[:8]}"
    secret = workspace / "secret.txt"
    secret.write_text("no access", encoding="utf-8")

    executor = _make_local_executor(workspace)
    exec_token = set_executor(executor)
    ws_token = workspace_root_var.set(str(workspace))
    chat_token = chat_id_var.set(chat_id)
    try:
        read_tool = create_file_read_tool(path_policy="evicted_uploaded")
        with pytest.raises(ToolError, match="blocked"):
            await read_tool.ainvoke(
                {"paths": ["secret.txt"], "mode": "all"},
                config=RunnableConfig(configurable={"chat_id": chat_id, "supports_vision": False}),
            )
    finally:
        reset_executor(exec_token)
        workspace_root_var.reset(ws_token)
        chat_id_var.reset(chat_token)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_converter_fast_request_wires_spill_and_uploads_on_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory_path = tmp_path / "memory"
    memory_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEMORY_BASE_PATH", str(memory_path))
    mock_configs = _build_mock_user_configs()
    mock_load = AsyncMock(return_value=mock_configs)

    request = AgentRequest(
        message_id="test-msg-fast-evicted-integ",
        chat_id="test-chat-fast-evicted-integ",
        query="Summarize a long policy page",
        model_selection=get_model_selection(),
        action_mode="fast",
        agent_config={"enabledBuiltinTools": ["web_search", "browser"]},
    )

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        mock_load,
    ):
        params, _, _, _, _ = await convert_to_general_agent_params(request, [])

    assert params.file_access_mode == FileAccessMode.SPILL_AND_UPLOADS
    assert params.enable_shell_tools is False
    assert params.prompt_mode == "search"

    agent = AgentFactory.create_general_agent(params)
    assert agent.file_access_mode == FileAccessMode.SPILL_AND_UPLOADS
    assert agent.enable_shell_tools is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fast_evicted_file_read_allows_uploaded_path_on_disk(
    workspace: Path,
) -> None:
    chat_id = f"chat-upload-integ-{uuid.uuid4().hex[:8]}"
    uploaded_dir = workspace / "_uploaded"
    uploaded_dir.mkdir(parents=True)
    report = uploaded_dir / "report.md"
    marker = "UPLOADED_INTEGRATION_MARKER"
    report.write_text(marker, encoding="utf-8")

    executor = _make_local_executor(workspace)
    exec_token = set_executor(executor)
    ws_token = workspace_root_var.set(str(workspace))
    chat_token = chat_id_var.set(chat_id)
    try:
        read_tool = create_file_read_tool(path_policy="evicted_uploaded")
        result = await read_tool.ainvoke(
            {"paths": ["_uploaded/report.md"], "mode": "all"},
            config=RunnableConfig(configurable={"chat_id": chat_id, "supports_vision": False}),
        )
    finally:
        reset_executor(exec_token)
        workspace_root_var.reset(ws_token)
        chat_id_var.reset(chat_token)

    assert isinstance(result, str)
    assert marker in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_bash_stdout_evicted_and_readable_via_file_read(
    workspace: Path,
) -> None:
    """Failed bash keeps large stdout recoverable: evicted on disk + file_read back.

    Real LocalExecutor failure path (no mock on execution/eviction): a command that
    prints a large stdout and then crashes must surface the truncation banner in the
    error and keep the full stdout readable from sandbox storage via file_read_tool.
    """
    chat_id = f"chat-fail-bash-{uuid.uuid4().hex[:8]}"
    executor = _make_local_executor(workspace)
    exec_token = set_executor(executor)
    ws_token = workspace_root_var.set(str(workspace))
    chat_token = chat_id_var.set(chat_id)
    result: str | None = None
    try:
        bash_tool = create_bash_code_execute_tool()
        config = RunnableConfig(
            configurable={
                "context": {
                    "session_id": chat_id,
                    "workspace_path": str(workspace),
                    "workspaces_storage_root": str(workspace),
                },
                "supports_vision": False,
            }
        )
        with (
            patch(
                "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
                AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.agent.skills.mcp.notify_registry.session_scope",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=None),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            pytest.raises(ToolError) as exc_info,
        ):
            await bash_tool.ainvoke(
                {
                    "command": ('python3 -c "import sys; [print(i) for i in range(2000)]; 1/0"'),
                    "reason": "integration verify failed bash stdout eviction",
                },
                config=config,
            )

        assert "[LARGE OUTPUT TRUNCATED (2000 lines" in str(exc_info.value)

        evicted_dir = workspace / ".context" / chat_id / "evicted"
        files = sorted(evicted_dir.glob("output_*.txt"))
        assert files, "failed stdout must be evicted to sandbox storage"
        rel = f".context/{chat_id}/evicted/{files[0].name}"

        read_tool = create_file_read_tool(path_policy="evicted_uploaded")
        read = await read_tool.ainvoke(
            {"paths": [rel], "mode": "all"},
            config=RunnableConfig(configurable={"chat_id": chat_id, "supports_vision": False}),
        )
        result = read if isinstance(read, str) else str(read)
    finally:
        reset_executor(exec_token)
        workspace_root_var.reset(ws_token)
        chat_id_var.reset(chat_token)

    assert result is not None
    disk_text = files[0].read_text(encoding="utf-8")
    assert "1999" in disk_text, "full stdout must be persisted to sandbox storage"
    assert files[0].name in result, "file_read must resolve the evicted file"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_bash_stderr_evicted_and_readable_via_file_read(
    workspace: Path,
) -> None:
    """Failed bash keeps large stderr recoverable: evicted on disk + file_read back.

    Symmetric to the stdout path: a command that writes a large stderr stream and
    then crashes must surface the truncation banner in the error and keep the full
    stderr readable from sandbox storage via file_read_tool.
    """
    chat_id = f"chat-fail-bash-stderr-{uuid.uuid4().hex[:8]}"
    executor = _make_local_executor(workspace)
    exec_token = set_executor(executor)
    ws_token = workspace_root_var.set(str(workspace))
    chat_token = chat_id_var.set(chat_id)
    result: str | None = None
    try:
        bash_tool = create_bash_code_execute_tool()
        config = RunnableConfig(
            configurable={
                "context": {
                    "session_id": chat_id,
                    "workspace_path": str(workspace),
                    "workspaces_storage_root": str(workspace),
                },
                "supports_vision": False,
            }
        )
        with (
            patch(
                "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
                AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.agent.skills.mcp.notify_registry.session_scope",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=None),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            pytest.raises(ToolError) as exc_info,
        ):
            await bash_tool.ainvoke(
                {
                    "command": ('python3 -c "import sys; [print(i, file=sys.stderr) for i in range(2000)]; 1/0"'),
                    "reason": "integration verify failed bash stderr eviction",
                },
                config=config,
            )

        assert "[LARGE OUTPUT TRUNCATED (" in str(exc_info.value)
        assert "ZeroDivisionError" in str(exc_info.value)

        evicted_dir = workspace / ".context" / chat_id / "evicted"
        files = sorted(evicted_dir.glob("output_*.txt"))
        assert files, "failed stderr must be evicted to sandbox storage"
        rel = f".context/{chat_id}/evicted/{files[0].name}"

        read_tool = create_file_read_tool(path_policy="evicted_uploaded")
        read = await read_tool.ainvoke(
            {"paths": [rel], "mode": "all"},
            config=RunnableConfig(configurable={"chat_id": chat_id, "supports_vision": False}),
        )
        result = read if isinstance(read, str) else str(read)
    finally:
        reset_executor(exec_token)
        workspace_root_var.reset(ws_token)
        chat_id_var.reset(chat_token)

    assert result is not None
    disk_text = files[0].read_text(encoding="utf-8")
    assert "1999" in disk_text, "full stderr must be persisted to sandbox storage"
    assert files[0].name in result, "file_read must resolve the evicted file"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skill_agent_build_tools_mounts_evicted_read_at_turn1() -> None:
    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.skill_agent import SkillAgent

    agent = SkillAgent(
        llm=AsyncMock(),
        file_access_mode=FileAccessMode.SPILL_AND_UPLOADS,
        enable_shell_tools=False,
    )
    agent.skill_backend = AsyncMock()
    agent.skill_backend.list_skills.return_value = []

    tools = await agent._build_tools()
    names = {tool.name for tool in tools}
    assert "file_read_tool" in names
    assert "file_write_tool" not in names
    assert "bash_code_execute_tool" not in names
