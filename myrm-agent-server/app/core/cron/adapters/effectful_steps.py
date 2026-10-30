"""Effectful step detection for cron runs.

[INPUT]
- myrm_agent_harness.agent.middlewares.completion::is_mutating_tool (POS: Effectful tool detection SSOT; unknown tools count as effectful)

[OUTPUT]
- has_effectful_tools: whether any recorded step is a call to a tool that changes state outside the run

[POS]
Server cron adapter. The one definition of "this run already did something a repeat would do again", shared by the
retry decision (`agent_runner`) and the post-run verification gate (`post_run_verification`).
"""

from __future__ import annotations

from myrm_agent_harness.agent.middlewares.completion import is_mutating_tool


def has_effectful_tools(progress_steps: list[dict[str, object]]) -> bool:
    """True when a step names a tool that mutates state; steps without a tool name (progress markers) are ignored."""
    for step in progress_steps:
        tool_name = step.get("tool_name")
        if isinstance(tool_name, str) and is_mutating_tool(tool_name):
            return True
    return False
