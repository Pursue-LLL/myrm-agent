"""Integration: project workspace bind → converter roots → file_write on bound disk."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import (
    create_file_write_tool,
)
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

from app.database.models.chat import Chat
from app.platform_utils import get_session_factory
from app.services.agent.params.models import AgentRequest, ModelSelection
from app.services.project.project_service import ProjectService

_DUMMY_CONFIG = RunnableConfig()


def _reset_workspace_cache() -> None:
    WorkspacePathResolver._cached_workspace_root = None


def _make_local_executor(workspace: Path) -> LocalExecutor:
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


async def _create_chat_in_project(chat_id: str, project_id: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="Project bind integration",
                project_id=project_id,
                action_mode="agent",
                source="web",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_project_bind_file_write_persists_to_bound_directory(
    tmp_path: Path,
) -> None:
    """Bind project workspace → converter declared_allowed_roots → file_write on disk."""
    vault = tmp_path / "obsidian-vault"
    vault.mkdir()

    project = await ProjectService.create_project("Bind File Write")
    project_id = str(project["id"])
    await ProjectService.update_project(project_id, workspace_path=str(vault))

    chat_id = f"c-bind-{uuid.uuid4().hex[:8]}"
    await _create_chat_in_project(chat_id, project_id)

    from tests.api.agent.conftest import _build_mock_user_configs
    from tests.api.agent.utils import _infer_provider_id

    mock_configs = _build_mock_user_configs()
    basic_model = os.environ.get("BASIC_MODEL", "minimax/MiniMax-M2.7")
    provider_id = _infer_provider_id(basic_model)

    request = AgentRequest(
        message_id=f"msg-{uuid.uuid4().hex[:8]}",
        chat_id=chat_id,
        query="Write hello.md with a short greeting.",
        action_mode="agent",
        model_selection=ModelSelection(
            provider_id=provider_id,
            model=basic_model,
            base_url=os.environ.get("BASIC_BASE_URL", "https://api.minimaxi.com/v1"),
        ),
        agent_config={"enabledBuiltinTools": ["file_ops"]},
    )

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        new=AsyncMock(return_value=mock_configs),
    ):
        from app.services.agent.params.converter import convert_to_general_agent_params

        params, _, _, _ = await convert_to_general_agent_params(request, [])

    assert params.declared_allowed_roots == (str(vault.resolve()),)

    _reset_workspace_cache()
    os.environ["WORKSPACE_ROOT"] = str(vault)
    bind_workspace_storage_root(vault)
    executor = _make_local_executor(vault)
    token = set_executor(executor)
    write_tool = create_file_write_tool()
    try:
        await write_tool.ainvoke(
            {"path": "hello.md", "content": "# Hello from project bind"},
            config=_DUMMY_CONFIG,
        )
    finally:
        reset_executor(token)
        os.environ.pop("WORKSPACE_ROOT", None)
        _reset_workspace_cache()

    written = vault / "hello.md"
    assert written.is_file()
    assert written.read_text(encoding="utf-8") == "# Hello from project bind"
