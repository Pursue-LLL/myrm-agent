"""build_middlewares tail: the request guards sit innermost so every other wrapper's edits reach them."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent._internals.agent_runtime import build_middlewares, create_registry
from myrm_agent_harness.agent.types import EngineParams


@pytest.mark.parametrize("parallel", [None, True, False])
def test_the_guards_are_the_last_wrappers_that_can_see_a_request_and_the_debug_logger_prints_its_view(
    parallel: bool | None,
) -> None:
    middlewares = build_middlewares(create_registry(), [], EngineParams(enable_parallel_tool_calls=parallel))

    assert [type(middleware).__name__ for middleware in middlewares[-3:]] == [
        "ThinkingReplayGuardMiddleware",
        "RequestViewGuardMiddleware",
        "DebugLoggerMiddleware",
    ]
