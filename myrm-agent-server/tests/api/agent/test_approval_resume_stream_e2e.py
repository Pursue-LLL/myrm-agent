"""Real-model turn that stops at an approval: the resume under the stopped turn's id streams the resumed turn.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, SSE back)
- A command the YOLO destructive-operation gate holds for approval (POS: stops the turn the way a user's approval card does)

[OUTPUT]
- Fails when the stream of the resume carries the stopped turn's approval again instead of what the approved run does next, or when it errors.

[POS]
The UI answers an approval card with a request under the id of the turn that asked, and reads that response as the rest of the turn. A server that
answers it with the stopped turn's buffered events shows the user the card again (or nothing) while the approved run finishes unseen.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection
from tests.support.real_model_workspace_turns import (
    TURN_TIMEOUT_SECONDS,
    new_chat,
    resume_request,
    stream_turn,
    turn_request,
)

PROMPT = (
    "Run exactly this one command with the bash tool and no other command, with no ';', '&&', pipe or redirect: "
    "rm -rf approval_resume_scratch . When it has run, reply with exactly: RESUME-DONE"
)

pytestmark = [
    pytest.mark.usefixtures("stuck_turn_report"),
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    pytest.mark.timeout(TURN_TIMEOUT_SECONDS, method="thread"),
]


def _asked_interrupt_ids(events: list[dict[str, object]]) -> set[str]:
    return {str(event["interruptId"]) for event in events if event.get("type") == "tool_approval_request"}


def test_a_resume_under_the_id_of_the_stopped_turn_streams_the_resumed_turn(client: TestClient) -> None:
    chat_id = new_chat(client)
    stopped_request = turn_request(PROMPT, chat_id, get_lite_model_selection())

    stopped = stream_turn(client, stopped_request)
    asked = _asked_interrupt_ids(stopped)
    assert asked, f"the model never ran the gated command; stream: {[event.get('type') for event in stopped]}"

    resumed = stream_turn(client, resume_request(stopped_request))

    check_e2e_errors(resumed)
    assert asked.isdisjoint(_asked_interrupt_ids(resumed)), (
        "the resume streamed the stopped turn's approval again instead of the resumed turn"
    )
    assert resumed != stopped
