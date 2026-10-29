"""The loop guard pause exactly as the harness streams it, for the tests of every consumer of that event."""

from __future__ import annotations

from types import SimpleNamespace

from myrm_agent_harness.agent.errors import ToolStuckException
from myrm_agent_harness.agent.streaming.interrupt_events import interrupt_events


def harness_pause_event(tool_name: str = "bash_code_execute_tool", tool_call_id: str = "call-1") -> dict[str, object]:
    """Built by the harness' own interrupt translator from a real ``ToolStuckException``, not a hand-written copy."""
    payload = ToolStuckException("stuck").interrupt_payload(tool_name, tool_call_id)
    [event] = interrupt_events([SimpleNamespace(value=payload, id="interrupt-1")], "msg-1", {})
    return event
