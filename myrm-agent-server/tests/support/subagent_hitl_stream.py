"""Shared HTTP agent-stream helpers for subagent HITL live / chrome E2E."""

from __future__ import annotations

import json
import uuid
from typing import Callable

import httpx

from tests.api.agent.utils import get_model_selection

_APPROVAL_EVENT_TYPES = frozenset({"approval_required", "tool_approval_request"})
_STREAM_TIMEOUT_SEC = 300.0
_MAX_RESUME_ROUNDS = 8


def consume_agent_stream(
    client: httpx.Client,
    api_base: str,
    payload: dict[str, object],
) -> tuple[str | None, list[dict[str, object]], list[dict[str, object]]]:
    events: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    action_type: str | None = None
    with client.stream(
        "POST",
        f"{api_base.rstrip('/')}/api/v1/agents/agent-stream",
        json=payload,
        timeout=_STREAM_TIMEOUT_SEC,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            event_type = event.get("type")
            if event_type in _APPROVAL_EVENT_TYPES:
                data = event.get("data")
                if isinstance(data, dict):
                    action_type = data.get("action_type")
                    if not isinstance(action_type, str):
                        action_type = "tool_approval"
            elif event_type == "error":
                errors.append(event)
    return action_type, events, errors


def completed_without_approval(events: list[dict[str, object]]) -> bool:
    has_message_end = any(e.get("type") == "message_end" for e in events)
    if not has_message_end:
        return False
    return not any(e.get("type") in _APPROVAL_EVENT_TYPES for e in events)


def build_subagent_stream_request(
    chat_id: str,
    message_id: str,
    query: str,
    *,
    agent_id: str,
    ephemeral_subagents: dict[str, dict[str, object]],
    resume_value: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    req: dict[str, object] = {
        "query": query,
        "chatId": chat_id,
        "messageId": message_id,
        "agentId": agent_id,
        "modelSelection": get_model_selection(),
        "actionMode": "general",
        "securityPreset": "hitl",
        "ephemeralSubagents": ephemeral_subagents,
    }
    if resume_value is not None:
        req["resumeValue"] = {"decisions": resume_value}
    return req


def run_until_subagent_approval(
    client: httpx.Client,
    api_base: str,
    chat_id: str,
    agent_id: str,
    query: str,
    *,
    ephemeral_subagents: dict[str, dict[str, object]],
) -> None:
    """Drive agent-stream over HTTP until subagent_approval interrupt (stream suspends)."""
    message_id = str(uuid.uuid4())
    resume_value: list[dict[str, object]] | None = None
    current_query = query

    for _round in range(_MAX_RESUME_ROUNDS):
        payload = build_subagent_stream_request(
            chat_id,
            message_id,
            current_query,
            agent_id=agent_id,
            ephemeral_subagents=ephemeral_subagents,
            resume_value=resume_value,
        )
        action_type, events, errors = consume_agent_stream(client, api_base, payload)

        if completed_without_approval(events):
            raise AssertionError(
                "Agent stream completed without approval — subagent bash did not suspend. "
                f"event_types={[e.get('type') for e in events]}"
            )
        if action_type == "subagent_approval":
            return
        if errors:
            raise AssertionError(f"agent-stream errors before subagent approval: {errors}")
        if action_type in (None, "tool_approval"):
            resume_value = [
                {"type": "approve", "feedback": "Auto-approve delegate_task_tool"}
            ]
            message_id = str(uuid.uuid4())
            current_query = ""
            continue
        break

    raise AssertionError(
        f"No subagent_approval after {_MAX_RESUME_ROUNDS} rounds; "
        f"last action_type={action_type!r}"
    )


def run_interrupt_flow(
    client: httpx.Client,
    api_base: str,
    chat_id: str,
    agent_id: str,
    query: str,
    *,
    ephemeral_subagents: dict[str, dict[str, object]],
    resume_decision_factory: Callable[
        [list[dict[str, object]]], list[dict[str, object]]
    ],
) -> None:
    """Full HTTP approve flow through subagent_approval → resume → message_end."""
    message_id = str(uuid.uuid4())
    resume_value: list[dict[str, object]] | None = None
    current_query = query
    approval_seen = False
    last_events: list[dict[str, object]] = []
    action_type: str | None = None

    for _round in range(_MAX_RESUME_ROUNDS):
        payload = build_subagent_stream_request(
            chat_id,
            message_id,
            current_query,
            agent_id=agent_id,
            ephemeral_subagents=ephemeral_subagents,
            resume_value=resume_value,
        )
        action_type, last_events, errors = consume_agent_stream(
            client, api_base, payload
        )

        if completed_without_approval(last_events):
            raise AssertionError(
                "Agent stream completed without approval event — "
                f"event_types={[e.get('type') for e in last_events]}"
            )
        if action_type == "subagent_approval":
            approval_seen = True
            resume_value = resume_decision_factory(last_events)
            message_id = str(uuid.uuid4())
            current_query = ""
            continue
        if errors:
            raise AssertionError(f"agent-stream errors before approval: {errors}")
        if action_type in (None, "tool_approval"):
            resume_value = [
                {"type": "approve", "feedback": "Auto-approve delegate_task_tool"}
            ]
            message_id = str(uuid.uuid4())
            current_query = ""
            continue
        break

    if not approval_seen:
        raise AssertionError(
            f"No subagent_approval after {_MAX_RESUME_ROUNDS} rounds; "
            f"last action_type={action_type!r} "
            f"events={[e.get('type') for e in last_events]}"
        )

    payload = build_subagent_stream_request(
        chat_id,
        message_id,
        "",
        agent_id=agent_id,
        ephemeral_subagents=ephemeral_subagents,
        resume_value=resume_value,
    )
    _action_type, resume_events, resume_errors = consume_agent_stream(
        client, api_base, payload
    )
    has_end = any(e.get("type") == "message_end" for e in resume_events)
    if not has_end:
        raise AssertionError(
            f"Agent did not complete after approval resume; "
            f"events={[e.get('type') for e in resume_events]} errors={resume_errors}"
        )
