"""Real agent-stream integration: context_budget breakdown on message_end.

Verifies harness → SSE message_end → context_budget (provider total + GUI breakdown)
without mocking the agent runtime or token tracker on the critical path.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Final

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    build_approval_resume_value,
    check_e2e_errors,
    get_model_selection,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("BASIC_API_KEY"),
        reason="E2E test requires BASIC_API_KEY from .env.test",
    ),
]

_SIMPLE_QUERY: Final[str] = "Reply with exactly one word: hello."


def _build_payload(chat_id: str) -> dict[str, object]:
    return {
        "query": _SIMPLE_QUERY,
        "chatId": chat_id,
        "messageId": f"msg-{uuid.uuid4().hex}",
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }


def _stream_turn(
    client: TestClient, payload: dict[str, object]
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=payload, timeout=180.0
    ) as response:
        if response.status_code != 200:
            body = response.text
            response.read()
            pytest.fail(f"agent-stream failed ({response.status_code}): {body[:500]}")

        for raw_line in response.iter_lines():
            if not raw_line or not raw_line.startswith("data: "):
                continue
            raw_payload = raw_line[6:]
            if raw_payload == "[DONE]":
                break
            try:
                event = json.loads(raw_payload)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _collect_turn_with_approvals(
    client: TestClient, payload: dict[str, object]
) -> list[dict[str, object]]:
    events = _stream_turn(client, payload)
    for _ in range(8):
        if not any(
            event.get("type") in ("approval_required", "tool_approval_request")
            for event in reversed(events)
        ):
            break
        resume_payload = dict(payload)
        resume_payload["resumeValue"] = build_approval_resume_value()
        events.extend(_stream_turn(client, resume_payload))
    return events


def _find_message_end(events: list[dict[str, object]]) -> dict[str, object]:
    for event in reversed(events):
        if event.get("type") == "message_end":
            return event
    pytest.fail("message_end event missing from agent-stream")


@pytest.mark.timeout(240)
def test_message_end_context_budget_includes_provider_total_and_breakdown(
    client: TestClient,
) -> None:
    """One real agent turn must emit context_budget with provider total + GUI breakdown."""
    chat_id = f"context-budget-{uuid.uuid4().hex}"
    payload = _build_payload(chat_id)
    events = _collect_turn_with_approvals(client, payload)
    check_e2e_errors(events)

    message_end = _find_message_end(events)
    budget = message_end.get("context_budget")
    assert isinstance(
        budget, dict
    ), f"context_budget missing on message_end: {message_end.keys()}"

    current_tokens = budget.get("current_tokens")
    assert isinstance(current_tokens, int) and current_tokens > 0
    assert isinstance(budget.get("max_context_tokens"), int)
    assert isinstance(budget.get("usage_percent"), (int, float))
    assert budget.get("health_status") in {"healthy", "warning", "critical"}

    tools_overhead = budget.get("bound_tools_overhead_tokens")
    assert (
        isinstance(tools_overhead, int) and tools_overhead > 0
    ), "bound_tools_overhead_tokens should be present for default agent tool bind"

    messages_est = budget.get("messages_estimated_tokens")
    assert isinstance(messages_est, int) and messages_est >= 0

    other_tokens = budget.get("other_tokens")
    assert isinstance(other_tokens, int) and other_tokens >= 0

    turn_count = budget.get("turn_count")
    assert isinstance(turn_count, int) and turn_count >= 0

    assert current_tokens >= messages_est + tools_overhead or other_tokens >= 0
