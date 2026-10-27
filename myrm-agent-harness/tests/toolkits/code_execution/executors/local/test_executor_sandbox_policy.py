"""The local executor hands each shell its run's workspace mode; it never assembles a sandbox policy itself."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.session.models import SessionConfig


@pytest.mark.asyncio
@pytest.mark.parametrize(("readonly", "network"), [(False, False), (True, False), (False, True)])
async def test_shell_config_carries_the_run_workspace_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path, readonly: bool, network: bool
) -> None:
    configs: list[SessionConfig] = []

    class _RecordingSession(AsyncMock):
        def __init__(self, config: SessionConfig) -> None:
            super().__init__()
            configs.append(config)

    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.code_execution.session.LocalPersistentSession", _RecordingSession
    )
    executor = LocalExecutor(config=ExecutionConfig(), workspace_path=str(tmp_path))
    context = ExecutionContext(code="true", session_id="s", readonly_workspace=readonly, allow_network=network)

    await executor._get_or_create_bash_session(context, {})

    assert [(c.readonly_workspace, c.allow_network, c.work_dir) for c in configs] == [(readonly, network, str(tmp_path))]
