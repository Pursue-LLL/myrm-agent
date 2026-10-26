"""A silent external CLI is not mistaken for a hung agent by the Gateway's idle watchdog.

The chain is real: ``RuntimePool`` -> ``CliRuntime`` -> a ``bash`` subprocess that says nothing for longer than
the Gateway tolerates -> ``stream_direct_delegate`` -> ``AgentGateway.execute_stream``. Only the time scale is
shrunk (production: 15 s keepalive against a 300 s idle limit).
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator

import pytest
from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.acp.runtime.cli import runtime as cli_runtime
from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig

from app.services.agent.gateway import AgentExecutionTimeout, AgentGateway, GatewayConfig
from app.services.external_agents.direct_delegate_stream import stream_direct_delegate

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="requires bash")

_IDLE_LIMIT_SECONDS = 0.5  # what the Gateway tolerates between two events
_CLI_SILENCE_SECONDS = 1.3  # the CLI says nothing for well past that


@pytest.fixture
async def pool() -> AsyncGenerator[RuntimePool]:
    pool = RuntimePool()
    pool.register(
        "quiet",
        RuntimeConfig(
            backend_type="cli",
            command="bash",
            args=["-c", f"sleep {_CLI_SILENCE_SECONDS}; echo finished"],
            timeout_seconds=30,
        ),
    )
    yield pool
    await pool.close_all()


async def _through_the_gateway(pool: RuntimePool) -> list[dict[str, object]]:
    gateway = AgentGateway(
        GatewayConfig(
            max_global=2,
            max_per_user=2,
            queue_timeout=1.0,
            execution_timeout=_IDLE_LIMIT_SECONDS,
            execution_hard_ceiling=30.0,
        )
    )
    turn = stream_direct_delegate(pool, "quiet", "go", session_id="quiet-chat")
    return [event async for event in gateway.execute_stream(turn, agent_type="test", session_id="quiet-chat")]


async def test_a_cli_silent_past_the_idle_limit_finishes_because_it_keeps_saying_it_is_working(
    pool: RuntimePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_runtime, "_KEEPALIVE_SECONDS", 0.1)

    events = await _through_the_gateway(pool)

    lines = [str(step["data"]) for step in events if step["type"] == AgentEventType.TASKS_STEPS.value]
    assert any("quiet: working" in line for line in lines)
    assert not any(event["type"] == AgentEventType.ERROR.value for event in events)
    assert events[-1]["type"] == AgentEventType.MESSAGE_END.value


async def test_without_the_keepalive_the_same_silence_is_cut_by_the_idle_limit(
    pool: RuntimePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_runtime, "_KEEPALIVE_SECONDS", 60.0)

    with pytest.raises(AgentExecutionTimeout):
        await _through_the_gateway(pool)
