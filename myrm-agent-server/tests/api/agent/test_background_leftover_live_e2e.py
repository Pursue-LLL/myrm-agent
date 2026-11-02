"""Real-model check that a model learns what a finished background job left running, and stops it with the same tool.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model (POS: the whole server path, a real provider call, real shell tools, SSE back)
- A background command that starts a long-lived child in its own process group and exits (POS: a job that ends and leaves a program behind)

[OUTPUT]
- Fails when the program the job leaves running was never seen running, when no ``bash_process_tool`` result names it, when no kill
  report says it was stopped, or when a process carrying the marker is still alive after the turn.

[POS]
What the tools report is decided by the harness; the model only has to call ``wait`` and ``kill`` on the job it started. The child sleeps for a
bounded time so a run in which the model never kills it cannot leave a process behind for long.
"""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection
from tests.support.marked_command_lines import leave_one_child_command, processes_with_marker
from tests.support.real_model_workspace_turns import TURN_TIMEOUT_SECONDS, new_chat, perform_agent_stream

pytestmark = [
    pytest.mark.usefixtures("stuck_turn_report"),
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    pytest.mark.timeout(TURN_TIMEOUT_SECONDS, method="thread"),
]

_CHILD_LIFETIME_SECONDS = 120
_LEFT_RUNNING = re.compile(r"leftover_processes\\*\"?\s*:\s*([1-9]\d*)")
_STOPPED_REPORT = "process(es) it left running"
_PROMPT = (
    "Use bash_code_execute_tool exactly once, with run_in_background=true, to run this command. Copy it exactly:\n"
    "{command}\n"
    "Then call bash_process_tool with action=wait for the pid of that job (timeout_seconds=20). "
    "If the result says the job left processes running, call bash_process_tool with action=kill for the same pid. "
    "Finally answer with the word DONE."
)


def _tool_message_texts(requests: Sequence[Sequence[Mapping[str, object]]]) -> list[str]:
    """Every tool result the model was handed, as it went into the requests after the call; a result repeats in each later request."""
    texts: list[str] = []
    for request in requests:
        for message in request:
            if message.get("role") != "tool":
                continue
            text = str(message.get("content"))
            if text not in texts:
                texts.append(text)
    return texts


@contextmanager
def _watching_for(marker: str) -> Iterator[list[bool]]:
    """Poll the process table while the turn runs; the single item turns true once a process carrying the marker was seen alive.

    Without this a process that never carried the marker (a command rewritten on its way to the shell) would count as stopped.
    """
    seen = [False]
    done = threading.Event()

    def poll() -> None:
        while not done.wait(0.2):
            if processes_with_marker(marker):
                seen[0] = True

    watcher = threading.Thread(target=poll, daemon=True)
    watcher.start()
    try:
        yield seen
    finally:
        done.set()
        watcher.join()


def _wait_until_gone(marker: str, timeout_seconds: float = 10.0) -> list[int]:
    deadline = time.monotonic() + timeout_seconds
    alive = processes_with_marker(marker)
    while alive and time.monotonic() < deadline:
        time.sleep(0.5)
        alive = processes_with_marker(marker)
    return alive


def test_model_is_told_what_a_finished_job_left_running_and_stops_it(
    client: TestClient, sent: list[list[dict[str, object]]]
) -> None:
    marker = f"MYRM_LANEC_LEFTOVER_{uuid.uuid4().hex[:10]}"
    chat_id = new_chat(client)

    with _watching_for(marker) as seen_running:
        _, events, _ = perform_agent_stream(
            client,
            _PROMPT.format(command=leave_one_child_command(marker, lifetime_seconds=_CHILD_LIFETIME_SECONDS)),
            chat_id,
            model_selection=get_lite_model_selection(),
        )
    check_e2e_errors(events)

    assert seen_running[0], "no process carrying the marker was ever seen running"
    handed_back = _tool_message_texts(sent)
    assert handed_back, "no tool result ever went back to the model"
    assert any(_LEFT_RUNNING.search(text) for text in handed_back), handed_back
    assert any(_STOPPED_REPORT in text for text in handed_back), handed_back
    assert _wait_until_gone(marker) == []
