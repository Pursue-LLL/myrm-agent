"""Real-model check that a model reads back what a background job printed when the host has no OS sandbox, as inside a container.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, real shell tools, SSE back)
- A host whose sandbox probe finds no OS sandbox (POS: ``tests/support/container_host.py``, the one part of the host that is stood in for)
- A background command that prints one line and ends at once (POS: the job whose output a pseudo-terminal can lose when it ends before the spawn returns)

[OUTPUT]
- Fails when no job was started on a pseudo-terminal, when one fell back to pipes, when no ``bash_process_tool`` result carries the line the job
  printed, or when the answer of the model does not.

[POS]
A host without an OS sandbox spawns every background job on a pseudo-terminal: containers and the hosted product. A developer Mac has the
sandbox on, so the same turn takes the pipe path there and never reaches the code this test is about. The command prints the line from two
pieces, so the whole line is in no request that carries the command and can only come from the output of the job.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection
from tests.support.container_host import record_pty_spawns, without_os_sandbox
from tests.support.real_model_workspace_turns import (
    TURN_TIMEOUT_SECONDS,
    new_chat,
    perform_agent_stream,
    tool_message_texts,
)

pytestmark = [
    pytest.mark.usefixtures("stuck_turn_report"),
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    pytest.mark.timeout(TURN_TIMEOUT_SECONDS, method="thread"),
]

_PROMPT = (
    "Use bash_code_execute_tool exactly once, with run_in_background=true, to run this command. Copy it exactly:\n"
    "{command}\n"
    "Then call bash_process_tool with action=wait for the pid of that job (timeout_seconds=20), "
    "then with action=output for the same pid. "
    "Finally answer with the one line the job printed and nothing else."
)


@pytest.fixture
def pty_spawns(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    without_os_sandbox(monkeypatch)
    return record_pty_spawns(monkeypatch)


def test_a_job_that_ends_at_once_is_read_back_whole_from_a_pty(
    client: TestClient, sent: list[list[dict[str, object]]], pty_spawns: list[bool]
) -> None:
    prefix, suffix = "BGOUT_", uuid.uuid4().hex[:10]
    printed = prefix + suffix
    chat_id = new_chat(client)

    answer, events, _ = perform_agent_stream(
        client,
        _PROMPT.format(command=f"python3 -c \"print('{prefix}' + '{suffix}')\""),
        chat_id,
        model_selection=get_lite_model_selection(),
    )
    check_e2e_errors(events)

    assert pty_spawns, "the job was not started on a pseudo-terminal"
    assert all(pty_spawns), f"a job fell back to pipes: {pty_spawns}"
    handed_back = tool_message_texts(sent)
    assert any(printed in text for text in handed_back), handed_back
    assert printed in answer, answer
