"""Live-stack API E2E: a live model saves a skill and the committed batch reaches the persisted Task Steps entry.

Task flow (no browser): a custom agent with only skill_manage mounted gets a plain request to save a skill; the
model calls ``skill_manage_tool``; the skill lands in the catalog with the SKILL.md the model sent; the server
announces the committed batch on the stream after the call's arguments and persists it on that step; rolling the
batch back (what the Undo dialog calls) removes the skill the batch created.

Run::

    ./myrm test -m e2e myrm-agent/myrm-agent-server/tests/api/agent/test_skill_manage_undo_live_api_e2e.py
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from urllib.parse import quote

import httpx
import pytest

from tests.support.bash_compressor_e2e import _backend_runtime_data_dir, resolve_working_base_selection
from tests.support.verify_api_base import resolve_verify_api_base

_SAVE_TOOL = "skill_manage_tool"
_FAILED_STATUSES = frozenset({"error", "cancelled"})
_DONE_TOKEN = "SKILL-MANAGE-API-E2E-DONE"
# The harness completion guard reads freshness words (live, latest, current, ...) in the request as a demand for web
# evidence, which a skill-only agent can never produce; the wording stays free of them so the turn ends on its own.
_SKILL_DESCRIPTION = "Skill saved by the API suite"
# Event types that carry a tool call's arguments (the step the batch id must later attach to).
_STEP_EVENT_TYPES = frozenset({"tasks_steps", "tool_start"})

_AGENT_SYSTEM_PROMPT = (
    f"You manage the user's skills with {_SAVE_TOOL}. When the user asks you to save a skill, call "
    f"{_SAVE_TOOL} exactly once with one operation: action=save, the given name and description, and a valid "
    "SKILL.md as content (YAML frontmatter with name and description, then the body the user asks for). "
    "Never claim a skill was saved without calling the tool. "
    "After the call finishes, reply with exactly the words the user asks for."
)


def _user_request(name: str, marker: str) -> str:
    return (
        f"Save a new skill with {_SAVE_TOOL}: one operation, action=save, name={name}, "
        f"description={_SKILL_DESCRIPTION}. The SKILL.md content is YAML frontmatter with that name and "
        f"description, then a heading, then one body line that is exactly: {marker} . "
        f"After it is saved, reply with exactly: {_DONE_TOKEN}"
    )


def _data(response: httpx.Response) -> dict[str, object]:
    """The ``data`` object of a standard API envelope, or the body itself when the route is not wrapped."""
    response.raise_for_status()
    body = response.json()
    assert isinstance(body, dict), body
    data = body.get("data")
    return data if isinstance(data, dict) else body


def _create_agent(client: httpx.Client, backend_url: str, suffix: str) -> str:
    """Custom agent with only skill_manage mounted; YOLO keeps approval cards out of the turn."""
    created = _data(
        client.post(
            f"{backend_url}/api/v1/user-agents",
            json={
                "name": f"Skill Manage API E2E {suffix}",
                "description": "Live API E2E agent that saves skills through skill_manage_tool",
                "system_prompt": _AGENT_SYSTEM_PROMPT,
                "skill_ids": [],
                "mcp_ids": [],
                "enabled_builtin_tools": ["skill_manage"],
                "security_overrides": {"yoloModeEnabled": True, "yolo_mode_enabled_at": time.time()},
            },
            timeout=60.0,
        )
    )
    agent_id = created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    return agent_id


def _create_chat(client: httpx.Client, backend_url: str, chat_id: str, agent_id: str) -> None:
    response = client.post(
        f"{backend_url}/api/v1/chats/",
        json={
            "chat_id": chat_id,
            "title": "Skill manage API E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    assert response.json().get("success") is True, response.text


def _stream_turn(client: httpx.Client, backend_url: str, agent_id: str, chat_id: str, query: str) -> list[dict[str, object]]:
    """Every event the stream delivered, in arrival order, until the server closes it."""
    request_data: dict[str, object] = {
        "messageId": f"live-skill-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": resolve_working_base_selection(backend_url=backend_url),
        "actionMode": "agent",
        "agentId": agent_id,
        "agentConfig": {"enabledBuiltinTools": ["skill_manage"], "skillIds": []},
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    events: list[dict[str, object]] = []
    with client.stream("POST", f"{backend_url}/api/v1/agents/agent-stream", json=request_data, timeout=600.0) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _batch_id_of(event: dict[str, object]) -> str | None:
    raw = event.get("skill_mutation_batch_id")
    nested = event.get("data")
    if raw is None and isinstance(nested, dict):
        raw = nested.get("skill_mutation_batch_id")
    return raw if isinstance(raw, str) and raw else None


def _stored_batch_ids(client: httpx.Client, backend_url: str, chat_id: str) -> list[str]:
    """Batch ids on the skill_manage steps the server persisted for the chat (a finished step has no status)."""
    messages = _data(client.get(f"{backend_url}/api/v1/chats/{chat_id}/messages", timeout=30.0)).get("messages")
    batch_ids: list[str] = []
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        metadata = message.get("metadata")
        steps = message.get("progressSteps") or (metadata.get("progressSteps") if isinstance(metadata, dict) else None)
        for step in steps if isinstance(steps, list) else []:
            if not (isinstance(step, dict) and str(step.get("tool_name") or "").endswith(_SAVE_TOOL)):
                continue
            batch_id = step.get("skill_mutation_batch_id")
            if step.get("status") not in _FAILED_STATUSES and isinstance(batch_id, str) and batch_id:
                batch_ids.append(batch_id)
    return batch_ids


def _catalog_skill_id(client: httpx.Client, backend_url: str, name: str) -> str | None:
    listing = client.get(f"{backend_url}/api/v1/skills/", timeout=30.0)
    listing.raise_for_status()
    for skill in listing.json().get("skills") or []:
        if isinstance(skill, dict) and skill.get("name") == name:
            return str(skill["id"])
    return None


def _wait_for[T](check: Callable[[], T], *, timeout_sec: float, what: str) -> T:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(2.0)
    pytest.fail(f"timed out after {timeout_sec:.0f}s waiting for {what}")


@pytest.mark.e2e
@pytest.mark.timeout(600)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY and LITE_API_KEY",
)
def test_live_agent_saves_a_skill_and_the_batch_reaches_its_step_and_rolls_back() -> None:
    backend_url = os.environ.get("BACKEND_URL", "").rstrip("/") or resolve_verify_api_base()
    if _backend_runtime_data_dir(backend_url) is None:
        pytest.skip(f"{backend_url} is not an isolated runtime; refusing to write skills into a shared backend")

    suffix = uuid.uuid4().hex[:8]
    skill_name = f"api-manage-{suffix}"
    marker = f"API_MARKER_{suffix}"
    chat_id = f"apimanage{suffix}"

    with httpx.Client() as client:
        agent_id = _create_agent(client, backend_url, suffix)
        _create_chat(client, backend_url, chat_id, agent_id)
        events = _stream_turn(client, backend_url, agent_id, chat_id, _user_request(skill_name, marker))

        batch_events = [(index, _batch_id_of(event)) for index, event in enumerate(events) if _batch_id_of(event)]
        assert batch_events, f"the stream never announced a committed batch; types: {[e.get('type') for e in events][:40]}"
        announced_at, announced_batch = batch_events[0]
        step_seen_at = next(
            (
                index
                for index, event in enumerate(events)
                if event.get("type") in _STEP_EVENT_TYPES
                and _SAVE_TOOL in json.dumps(event, default=str)
                and not _batch_id_of(event)
            ),
            None,
        )
        print(f"E2E_BATCH_ANNOUNCED: batch={announced_batch} step_event={step_seen_at} batch_event={announced_at}", flush=True)
        assert step_seen_at is not None and step_seen_at < announced_at, (
            f"the skill_manage step must reach the stream before its batch id: step={step_seen_at} batch={announced_at}"
        )

        stored = _wait_for(
            lambda: _stored_batch_ids(client, backend_url, chat_id), timeout_sec=60.0, what="the persisted step batch id"
        )
        assert announced_batch in stored, f"persisted batch ids {stored} do not include the announced {announced_batch}"

        skill_id = _catalog_skill_id(client, backend_url, skill_name)
        assert skill_id, f"skill {skill_name!r} is not in the catalog after the live turn"
        saved = client.get(f"{backend_url}/api/v1/skills/{quote(skill_id, safe='')}/files/SKILL.md", timeout=30.0)
        saved.raise_for_status()
        assert marker in saved.text, f"the saved SKILL.md lost the marker the user asked for:\n{saved.text[:600]}"

        rollback_url = f"{backend_url}/api/v1/skill-optimization/mutations/{announced_batch}/rollback"
        rolled_back = _data(client.post(rollback_url, timeout=60.0))
        assert rolled_back.get("status"), rolled_back
        _wait_for(
            lambda: _catalog_skill_id(client, backend_url, skill_name) is None,
            timeout_sec=60.0,
            what="the skill to disappear after the rollback",
        )
