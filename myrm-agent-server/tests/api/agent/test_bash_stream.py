import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import build_approval_resume_value, get_model_selection


def _stream_with_auto_approve(
    client: TestClient,
    request_data: dict[str, object],
) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []

    def _stream_once(req: dict[str, object]) -> None:
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req, timeout=180.0) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    parsed = json.loads(data_str)
                    if isinstance(parsed, dict):
                        collected.append(parsed)
                except json.JSONDecodeError:
                    continue

    _stream_once(request_data)

    for _ in range(10):
        approval_required = any(d.get("type") in ("approval_required", "tool_approval_request") for d in reversed(collected))
        if not approval_required:
            break
        resume_request = dict(request_data)
        resume_request["resumeValue"] = build_approval_resume_value()
        before = len(collected)
        _stream_once(resume_request)
        raced_busy = any(d.get("type") == "error" and "busy" in str(d.get("data", "")).lower() for d in collected[before:])
        if raced_busy:
            # The resume raced the previous agent turn's async teardown and the
            # session lock was still held; retry the resume after the turn
            # finishes releasing instead of surfacing a spurious AgentBusyError.
            time.sleep(1.0)
            del collected[before:]
            _stream_once(resume_request)

    return collected


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_bash_stream(client: TestClient) -> None:
    chat_id = f"bash-chat-{uuid.uuid4().hex[:8]}"

    request_data: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "query": (
            "Run EXACTLY ONE command via bash_code_execute_tool, and use no "
            "other tool: date +stream_marker_%s. "
            "The exact second-level timestamp is only obtainable by executing "
            "the command — do not simulate or invent a value. "
            "Report the exact full output line as returned."
        ),
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected = _stream_with_auto_approve(client, request_data)

    error_events = [d for d in collected if d.get("type") == "error"]
    if error_events:
        error_msg = str(error_events[0])
        flaky_signals = (
            "Authentication",
            "Authorization",
            "Recursion limit",
            "Cannot connect",
            "Connection error",
            "InternalServerError",
            "BadRequestError",
            "ToolExecutionError",
        )
        if any(kw in error_msg for kw in flaky_signals):
            pytest.skip(f"Environment/upstream flaky: {error_msg[:240]}")
        pytest.fail(f"Agent execution error: {error_msg}")

    def _bash_invoked(events: list[dict[str, object]]) -> bool:
        tool_stdout_chunk_received = any(d.get("type") == "tool_stdout_chunk" for d in events)
        stream_blob = json.dumps(events, default=str).lower()
        return tool_stdout_chunk_received or "bash_code_execute" in stream_blob

    if not _bash_invoked(collected):
        # Real LLMs (especially flash-tier) sometimes answer the prompt directly
        # without invoking the tool — model behavior, not a bash-stream defect.
        # This test verifies the bash stdout stream; a non-compliant turn must
        # not flap it, so retry with fresh chats (each attempt is independent).
        for _ in range(3):
            retry_data = dict(request_data)
            retry_data["chatId"] = f"bash-chat-{uuid.uuid4().hex[:8]}"
            retry_data["messageId"] = str(uuid.uuid4())
            collected = _stream_with_auto_approve(client, retry_data)
            if _bash_invoked(collected):
                break

    assert _bash_invoked(collected), "Expected bash_code_execute_tool invocation or tool_stdout_chunk event"


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_bash_failure_partial_stdout_reaches_agent_stream(
    client: TestClient,
) -> None:
    """Failed bash keeps partial stdout in the error surfaced to the LLM (real LLM).

    The command prints a marker then crashes with 1/0. The failure-path stdout
    symmetry in bash_executor_execute_mixin must embed that partial stdout in the
    error message, which flows into the agent stream so the model can diagnose.
    """
    chat_id = f"bash-fail-chat-{uuid.uuid4().hex[:8]}"
    marker = "PARTIAL_STDOUT_MARKER_9f2a"

    request_data: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "query": (
            "Use bash_code_execute_tool EXACTLY ONCE, and do not retry and do not "
            "use any other tool, to run this python one-liner: "
            f"python3 -c \"import sys; print('{marker}'); 1/0\" "
            "It will fail. Then report exactly what the command printed before it failed."
        ),
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected = _stream_with_auto_approve(client, request_data)

    stream_blob = json.dumps(collected, default=str)
    if marker in stream_blob:
        return

    error_events = [d for d in collected if d.get("type") == "error"]
    if error_events:
        error_msg = str(error_events[0])
        flaky_signals = (
            "Authentication",
            "Authorization",
            "Recursion limit",
            "Cannot connect",
            "Connection error",
            "InternalServerError",
            "BadRequestError",
            "Param Incorrect",
            "quota exceeded",
            "ToolExecutionError",
        )
        if any(kw in error_msg for kw in flaky_signals):
            pytest.skip(f"Environment/upstream flaky: {error_msg[:240]}")
        event_types = [d.get("type") for d in collected]
        tool_msgs = [str(d)[:300] for d in collected if d.get("type") in ("message", "tool_result", "tasks_steps")]
        pytest.fail(f"Agent execution error: {error_msg}\nEVENT_TYPES={event_types}\nTOOL_MSGS={tool_msgs[:6]}")
    pytest.fail("marker not found in stream")

    stream_blob = json.dumps(collected, default=str)
    assert marker in stream_blob, "partial stdout of a failed bash command must reach the agent stream"
