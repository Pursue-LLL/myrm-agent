"""Every memory-context test starts and ends without the telemetry an earlier call left on the run's context.

The middleware publishes the budget gauge and the injection status through ContextVars that the server reads after the
call. A value left over from one test would make the next one read the answer of a call it never made.

[INPUT]
- agent.skill_agent.context::set_memory_runtime_budget / set_memory_runtime_injection (POS: the channels a call publishes its gauge and status through)

[POS]
Per-test reset of the memory telemetry channels.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent.skill_agent.context import set_memory_runtime_budget, set_memory_runtime_injection


@pytest.fixture(autouse=True)
def _reset_runtime_memory_telemetry() -> Iterator[None]:
    set_memory_runtime_budget(None)
    set_memory_runtime_injection(None)
    yield
    set_memory_runtime_budget(None)
    set_memory_runtime_injection(None)
