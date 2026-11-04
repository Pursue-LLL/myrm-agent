"""The bash timeout floor for MCP skills: the script outlives the longest limit configured for the servers it can call.

A script that calls a tool configured with ``execute_timeout=300`` is not done at 120 s. If the host ended the script
there, the error that names the stuck tool could never reach it, and the call would die without a reason.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.constants import MCP_HOST_MARGIN_SECONDS, MCP_MIN_TIMEOUT
from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.toolkits.code_execution import MCPConfigItem


@pytest.fixture
def executor() -> BashExecutor:
    code_executor = MagicMock()
    code_executor.config = MagicMock()
    return BashExecutor(code_executor, enable_skill_execution=False)


def _servers(*execute_timeouts: float) -> list[MCPConfigItem]:
    return [MCPConfigItem(name=f"srv{i}", execute_timeout=limit) for i, limit in enumerate(execute_timeouts)]


@pytest.mark.parametrize("requested", [None, 5, 100])
def test_a_long_configured_limit_lifts_a_short_request_above_it(executor: BashExecutor, requested: int | None) -> None:
    assert executor._maybe_extend_timeout_for_mcp(_servers(300.0), requested) == 300 + MCP_HOST_MARGIN_SECONDS


def test_the_longest_limit_among_the_skills_servers_counts(executor: BashExecutor) -> None:
    assert executor._maybe_extend_timeout_for_mcp(_servers(60.0, 200.0, 90.0), None) == 200 + MCP_HOST_MARGIN_SECONDS


def test_short_limits_keep_the_static_floor(executor: BashExecutor) -> None:
    assert executor._maybe_extend_timeout_for_mcp(_servers(10.0), 5) == MCP_MIN_TIMEOUT


def test_the_default_limit_is_outlived_too(executor: BashExecutor) -> None:
    default_limit = MCPConfigItem(name="demo").execute_timeout

    floor = executor._maybe_extend_timeout_for_mcp([MCPConfigItem(name="demo")], None)

    assert floor == default_limit + MCP_HOST_MARGIN_SECONDS


def test_a_fractional_limit_rounds_up_so_the_host_never_ends_first(executor: BashExecutor) -> None:
    assert executor._maybe_extend_timeout_for_mcp(_servers(130.5), None) == 161


def test_a_request_above_the_floor_is_left_alone(executor: BashExecutor) -> None:
    assert executor._maybe_extend_timeout_for_mcp(_servers(300.0), 900) == 900


def test_a_skill_without_mcp_servers_is_left_alone(executor: BashExecutor) -> None:
    assert executor._maybe_extend_timeout_for_mcp(None, 30) == 30
    assert executor._maybe_extend_timeout_for_mcp([], None) is None
