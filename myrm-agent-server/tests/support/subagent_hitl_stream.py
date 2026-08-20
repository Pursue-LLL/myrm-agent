"""Shared HTTP agent-stream helpers for subagent HITL live / chrome E2E."""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Callable

import httpx

from tests.support.e2e_provider_seed import build_e2e_model_selection
from tests.support.e2e_runtime_guard import heartbeat_once

_APPROVAL_EVENT_TYPES = frozenset({"approval_required", "tool_approval_request"})
_STREAM_TIMEOUT_SEC = 300.0
_STREAM_ROUND_WALL_SEC = 600.0
_STREAM_IDLE_AFTER_MEANINGFUL_SEC = 180.0
_MAX_RESUME_ROUNDS = 8
_PROGRESS_EVENT_TYPES = frozenset(
    {
        "message_start",
        "message_end",
        "approval_required",
        "tool_approval_request",
        "tool_call_start",
        "tool_call_end",
        "subagent_start",
        "subagent_end",
        "error",
        "content_delta",
        "progress",
        "tools_snapshot",
        "tasks_steps",
        "status",
        "capability_gap",
    }
)


def _log_progress(message: str) -> None:
    print(f"SUBAGENT_HITL_STREAM: {message}", file=sys.stderr, flush=True)


def _stream_terminal_risk_blocked(events: list[dict[str, object]]) -> str | None:
    for event in events:
        if event.get("type") != "risk_blocked":
            continue
        data = event.get("data")
        if isinstance(data, dict):
            message = data.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
            rules = data.get("rules")
            if isinstance(rules, list) and rules:
                names = [str(item.get("display_name")) for item in rules if isinstance(item, dict) and item.get("display_name")]
                if names:
                    return f"risk_blocked: {', '.join(names)}"
        return "risk_blocked by input risk gate"
    return None


def consume_agent_stream(
    client: httpx.Client,
    api_base: str,
    payload: dict[str, object],
) -> tuple[str | None, list[dict[str, object]], list[dict[str, object]]]:
    events: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    action_type: str | None = None
    round_started = time.monotonic()
    last_progress = round_started
    with client.stream(
        "POST",
        f"{api_base.rstrip('/')}/api/v1/agents/agent-stream",
        json=payload,
        timeout=httpx.Timeout(_STREAM_TIMEOUT_SEC, read=120.0),
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            heartbeat_once()
            now = time.monotonic()
            if now - round_started > _STREAM_ROUND_WALL_SEC:
                raise TimeoutError(
                    f"agent-stream round exceeded {_STREAM_ROUND_WALL_SEC}s wall (event_types={[e.get('type') for e in events]})"
                )
            if now - last_progress > _STREAM_IDLE_AFTER_MEANINGFUL_SEC:
                raise TimeoutError(
                    f"agent-stream idle >{_STREAM_IDLE_AFTER_MEANINGFUL_SEC}s "
                    f"without progress (event_types={[e.get('type') for e in events]})"
                )
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
            if event_type == "tools_snapshot":
                data = event.get("data")
                tool_names: list[str] = []
                rows = data if isinstance(data, list) else None
                if isinstance(data, dict):
                    tools = data.get("tools")
                    if isinstance(tools, list):
                        rows = tools
                if isinstance(rows, list):
                    for item in rows:
                        if isinstance(item, dict):
                            name = item.get("name")
                            if isinstance(name, str):
                                tool_names.append(name)
                _log_progress(
                    f"tools_snapshot count={len(tool_names)} "
                    f"has_delegate={'delegate_task_tool' in tool_names or 'delegate_task' in tool_names}"
                )
            if event_type in _PROGRESS_EVENT_TYPES:
                last_progress = now
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
        "modelSelection": build_e2e_model_selection(use_lite=True),
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

    for round_idx in range(_MAX_RESUME_ROUNDS):
        heartbeat_once()
        _log_progress(
            f"run_until_subagent_approval round={round_idx + 1} resume={resume_value is not None} query_len={len(current_query)}"
        )
        payload = build_subagent_stream_request(
            chat_id,
            message_id,
            current_query,
            agent_id=agent_id,
            ephemeral_subagents=ephemeral_subagents,
            resume_value=resume_value,
        )
        action_type, events, errors = consume_agent_stream(client, api_base, payload)
        _log_progress(f"round={round_idx + 1} action_type={action_type!r} event_types={[e.get('type') for e in events]}")

        if completed_without_approval(events):
            raise AssertionError(
                "Agent stream completed without approval — subagent bash did not suspend. "
                f"event_types={[e.get('type') for e in events]}"
            )
        blocked = _stream_terminal_risk_blocked(events)
        if blocked is not None:
            raise AssertionError(f"Input risk gate blocked delegate query — revise E2E prompt: {blocked}")
        if action_type == "subagent_approval":
            return
        if errors:
            raise AssertionError(f"agent-stream errors before subagent approval: {errors}")
        if action_type in (None, "tool_approval"):
            resume_value = [{"type": "approve", "feedback": "Auto-approve delegate_task_tool"}]
            message_id = str(uuid.uuid4())
            current_query = ""
            continue
        break

    raise AssertionError(f"No subagent_approval after {_MAX_RESUME_ROUNDS} rounds; last action_type={action_type!r}")


def run_interrupt_flow(
    client: httpx.Client,
    api_base: str,
    chat_id: str,
    agent_id: str,
    query: str,
    *,
    ephemeral_subagents: dict[str, dict[str, object]],
    resume_decision_factory: Callable[[list[dict[str, object]]], list[dict[str, object]]],
) -> None:
    """Full HTTP approve flow through subagent_approval → resume → message_end."""
    message_id = str(uuid.uuid4())
    resume_value: list[dict[str, object]] | None = None
    current_query = query
    approval_seen = False
    last_events: list[dict[str, object]] = []
    action_type: str | None = None

    for round_idx in range(_MAX_RESUME_ROUNDS):
        heartbeat_once()
        _log_progress(
            f"run_interrupt_flow round={round_idx + 1} resume={resume_value is not None} query_len={len(current_query)}"
        )
        payload = build_subagent_stream_request(
            chat_id,
            message_id,
            current_query,
            agent_id=agent_id,
            ephemeral_subagents=ephemeral_subagents,
            resume_value=resume_value,
        )
        action_type, last_events, errors = consume_agent_stream(client, api_base, payload)
        _log_progress(f"round={round_idx + 1} action_type={action_type!r} event_types={[e.get('type') for e in last_events]}")

        if completed_without_approval(last_events) and not approval_seen:
            raise AssertionError(
                f"Agent stream completed without approval event — event_types={[e.get('type') for e in last_events]}"
            )
        if approval_seen and any(e.get("type") == "message_end" for e in last_events):
            _log_progress("run_interrupt_flow completed after subagent approval resume")
            return
        blocked = _stream_terminal_risk_blocked(last_events)
        if blocked is not None:
            raise AssertionError(f"Input risk gate blocked delegate query — revise E2E prompt: {blocked}")
        if action_type == "subagent_approval":
            approval_seen = True
            resume_value = resume_decision_factory(last_events)
            message_id = str(uuid.uuid4())
            current_query = ""
            continue
        if errors:
            raise AssertionError(f"agent-stream errors before approval: {errors}")
        if action_type in (None, "tool_approval"):
            resume_value = [{"type": "approve", "feedback": "Auto-approve delegate_task_tool"}]
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

    _log_progress("run_interrupt_flow final resume after subagent_approval")
    payload = build_subagent_stream_request(
        chat_id,
        message_id,
        "",
        agent_id=agent_id,
        ephemeral_subagents=ephemeral_subagents,
        resume_value=resume_value,
    )
    _action_type, resume_events, resume_errors = consume_agent_stream(client, api_base, payload)
    _log_progress(f"final resume action_type={_action_type!r} event_types={[e.get('type') for e in resume_events]}")
    has_end = any(e.get("type") == "message_end" for e in resume_events)
    if not has_end:
        raise AssertionError(
            f"Agent did not complete after approval resume; "
            f"events={[e.get('type') for e in resume_events]} errors={resume_errors}"
        )
