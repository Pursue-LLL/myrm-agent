"""Live integration: real CLI timeout cleanup through the chat-scoped pool.

Spawns a real ``bash`` subprocess via the full chain
(ExternalAgentsMixin -> ChatRuntimePoolRegistry -> ChatScopedRuntimePoolFacade
-> RuntimePool -> CliRuntime) and verifies that a timed-out turn terminates the
process (no orphan) while keeping the pool reusable for the next message.
"""

from __future__ import annotations

import sys

import pytest
from myrm_agent_harness.toolkits.acp.types import RuntimeEventType

from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin
from app.services.external_agents.runtime_pool_registry import (
    ChatScopedRuntimePoolFacade,
    get_chat_runtime_pool_registry,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="requires bash"),
]

_SLEEP_AGENT_CFG: list[dict[str, object]] = [
    {
        "name": "bash-sleep",
        "type": "cli",
        "command": "bash",
        "args": ["-c", "sleep 30"],
        "timeout": 1,
    }
]


@pytest.fixture(autouse=True)
async def _reset_registry() -> None:
    await get_chat_runtime_pool_registry().close_all()
    yield
    await get_chat_runtime_pool_registry().close_all()


def _new_mixin(*, chat_scope_id: str) -> ExternalAgentsMixin:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = _SLEEP_AGENT_CFG
    mixin._runtime_pool_scope_id = chat_scope_id
    mixin._runtime_pool = None
    mixin._runtime_pool_from_registry = False
    mixin._runtime_pool_ephemeral = False
    mixin.agent_id = "general"
    mixin.force_delegate_agent = None
    return mixin


@pytest.mark.asyncio
async def test_real_cli_timeout_terminates_process_and_pool_reusable() -> None:
    """A timed-out turn must kill the spawned process and keep the pool alive."""
    chat_id = "live-int-timeout-cleanup"
    mixin = _new_mixin(chat_scope_id=chat_id)
    await mixin._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)

    pool = mixin._runtime_pool
    assert isinstance(pool, ChatScopedRuntimePoolFacade)
    raw_pool = pool._pool
    cli = raw_pool.get("bash-sleep")

    events = [e async for e in raw_pool.run_turn("bash-sleep", "hi", "sess-1")]

    error_events = [e for e in events if e.type == RuntimeEventType.ERROR]
    assert error_events, "timeout must surface an ERROR event"
    assert error_events[0].data["error"].code.value == "timeout"

    proc = cli._process
    assert proc is not None, "process must have been spawned before cleanup"
    assert proc.returncode is not None, "timed-out process must be terminated (no orphan)"

    # The same pool stays registered for the chat and spawns a fresh process.
    mixin_b = _new_mixin(chat_scope_id=chat_id)
    await mixin_b._do_setup_external_agents([], mount_invoke_acp_agent_tool=False)
    assert isinstance(mixin_b._runtime_pool, ChatScopedRuntimePoolFacade)
    assert mixin_b._runtime_pool._pool is raw_pool

    events2 = [e async for e in raw_pool.run_turn("bash-sleep", "hi", "sess-1")]
    assert any(e.type == RuntimeEventType.ERROR for e in events2)
    assert cli._process is not None
    assert cli._process.returncode is not None
