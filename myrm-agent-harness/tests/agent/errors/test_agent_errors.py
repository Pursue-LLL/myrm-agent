"""The interrupt value of a ToolStuckException: how a host tells a guard pause from an approval."""

from __future__ import annotations

from myrm_agent_harness.agent.errors import TOOL_STUCK_ACTION_TYPE, ToolStuckException


def test_interrupt_payload_names_the_pause_and_the_failing_call() -> None:
    payload = ToolStuckException("stuck on the same call").interrupt_payload("bash_code_execute_tool", "call-1")

    assert payload == {
        "action_type": TOOL_STUCK_ACTION_TYPE,
        "tool_name": "bash_code_execute_tool",
        "tool_call_id": "call-1",
        "error_message": "stuck on the same call",
    }


def test_action_type_is_the_literal_every_host_matches_on() -> None:
    # The web client and the server match this literal off the wire; renaming it breaks both without a type error.
    assert TOOL_STUCK_ACTION_TYPE == "tool_stuck"
