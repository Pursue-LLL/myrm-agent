"""Shared steps of the live-stack skill_manage API E2E tests.

[INPUT]
- tests.support.verify_api_base::resolve_verify_api_base (POS: isolated verify backend URL)
- tests.support.bash_compressor_e2e (POS: backend runtime-dir probe, working model selection)

[OUTPUT]
- isolated_backend_url / requires_live_model: the guards every live test starts with
- create_agent / create_chat / stream_turn: a skill-only agent, its chat, and one streamed turn
- user_request / rewrite_request / patch_request / delete_request: the plain requests the model is given
- batch_id_of / announced_batch / announced_batches / persisted_skill_steps / stored_batch_ids / catalog_skill_id /
  skill_md / wait_for: what the tests read back from the stream and the API

[POS]
Support module of ``test_skill_manage_undo_live_api_e2e.py``. The harness completion guard reads freshness words
(live, latest, current, ...) in the request as a demand for web evidence, which a skill-only agent can never produce;
the request and system-prompt wording stays free of them so a turn ends on its own.
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

SAVE_TOOL = "skill_manage_tool"
FAILED_STATUSES = frozenset({"error", "cancelled"})
DONE_TOKEN = "SKILL-MANAGE-API-E2E-DONE"
SKILL_DESCRIPTION = "Skill saved by the API suite"
# Event types that carry a tool call's arguments (the step the batch id must later attach to).
STEP_EVENT_TYPES = frozenset({"tasks_steps", "tool_start"})

requires_live_model = pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY and LITE_API_KEY",
)

_AGENT_SYSTEM_PROMPT = (
    f"You manage the user's skills with {SAVE_TOOL}. When the user asks you to save a skill, call "
    f"{SAVE_TOOL} exactly once with one operation: action=save, the given name and description, and a valid "
    "SKILL.md as content (YAML frontmatter with name and description, then the body the user asks for). "
    f"When the user asks you to delete a skill, call {SAVE_TOOL} exactly once with one operation: "
    "action=delete and the given name. "
    f"When the user asks you to patch a skill, call {SAVE_TOOL} exactly once with one operation: action=patch, "
    "the given name, old_content (the exact fragment to replace) and new_content. "
    "Never claim a skill was saved, patched or deleted without calling the tool. "
    "After the call finishes, reply with exactly the words the user asks for."
)


def isolated_backend_url() -> str:
    """The verify backend the test may write skills into; skips when it is not an isolated runtime."""
    backend_url = os.environ.get("BACKEND_URL", "").rstrip("/") or resolve_verify_api_base()
    if _backend_runtime_data_dir(backend_url) is None:
        pytest.skip(f"{backend_url} is not an isolated runtime; refusing to write skills into a shared backend")
    return backend_url


def user_request(name: str, marker: str) -> str:
    return (
        f"Save a new skill with {SAVE_TOOL}: one operation, action=save, name={name}, "
        f"description={SKILL_DESCRIPTION}. The SKILL.md content is YAML frontmatter with that name and "
        f"description, then a heading, then one body line that is exactly: {marker} . "
        f"After it is saved, reply with exactly: {DONE_TOKEN}"
    )


def rewrite_request(name: str, marker: str) -> str:
    return (
        f"Save the skill {name} again with {SAVE_TOOL}: one operation, action=save, the same name and "
        f"description={SKILL_DESCRIPTION}. The new SKILL.md content is YAML frontmatter with that name and "
        f"description, then a heading, then one body line that is exactly: {marker} . "
        f"After it is saved, reply with exactly: {DONE_TOKEN}"
    )


def delete_request(name: str) -> str:
    return (
        f"Delete the skill {name} with {SAVE_TOOL}: one operation, action=delete, name={name}. "
        f"After it is deleted, reply with exactly: {DONE_TOKEN}"
    )


def patch_request(name: str, old: str, new: str) -> str:
    return (
        f"Patch the skill {name} with {SAVE_TOOL}: one operation, action=patch, name={name}, "
        f"old_content={old}, new_content={new}. After it is patched, reply with exactly: {DONE_TOKEN}"
    )


def data(response: httpx.Response) -> dict[str, object]:
    """The ``data`` object of a standard API envelope, or the body itself when the route is not wrapped."""
    response.raise_for_status()
    body = response.json()
    assert isinstance(body, dict), body
    payload = body.get("data")
    return payload if isinstance(payload, dict) else body


def create_agent(client: httpx.Client, backend_url: str, suffix: str) -> str:
    """Custom agent with only skill_manage mounted; YOLO keeps approval cards out of the turn."""
    created = data(
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


def create_chat(client: httpx.Client, backend_url: str, chat_id: str, agent_id: str) -> None:
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


def stream_turn(client: httpx.Client, backend_url: str, agent_id: str, chat_id: str, query: str) -> list[dict[str, object]]:
    """Every event the stream delivered, in arrival order, until the server closes it; prints the model it ran on."""
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
    print(f"E2E_MODEL_USED: {', '.join(_models_used(events)) or 'unreported'}")
    return events


def _models_used(events: list[dict[str, object]]) -> list[str]:
    """The model names the server billed the turn to, as its closing ``message_end`` event reports them."""
    names: set[str] = set()
    for event in events:
        usage = event.get("usage")
        model_usage = usage.get("model_usage") if event.get("type") == "message_end" and isinstance(usage, dict) else None
        if isinstance(model_usage, dict):
            names.update(str(name) for name in model_usage)
    return sorted(names)


def batch_id_of(event: dict[str, object]) -> str | None:
    raw = event.get("skill_mutation_batch_id")
    nested = event.get("data")
    if raw is None and isinstance(nested, dict):
        raw = nested.get("skill_mutation_batch_id")
    return raw if isinstance(raw, str) and raw else None


def announced_batch(events: list[dict[str, object]]) -> str | None:
    return next((batch_id for event in events if (batch_id := batch_id_of(event))), None)


def announced_batches(events: list[dict[str, object]]) -> set[str]:
    return {batch_id for event in events if (batch_id := batch_id_of(event))}


def skill_md(client: httpx.Client, backend_url: str, skill_id: str) -> str:
    response = client.get(f"{backend_url}/api/v1/skills/{quote(skill_id, safe='')}/files/SKILL.md", timeout=30.0)
    response.raise_for_status()
    return response.text


def persisted_skill_steps(client: httpx.Client, backend_url: str, chat_id: str) -> list[dict[str, object]]:
    """The skill_manage steps the server persisted for the chat, as the chat view loads them."""
    messages = data(client.get(f"{backend_url}/api/v1/chats/{chat_id}/messages", timeout=30.0)).get("messages")
    persisted: list[dict[str, object]] = []
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        metadata = message.get("metadata")
        steps = message.get("progressSteps") or (metadata.get("progressSteps") if isinstance(metadata, dict) else None)
        persisted.extend(
            step
            for step in (steps if isinstance(steps, list) else [])
            if isinstance(step, dict) and str(step.get("tool_name") or "").endswith(SAVE_TOOL)
        )
    return persisted


def stored_batch_ids(client: httpx.Client, backend_url: str, chat_id: str) -> list[str]:
    """Batch ids on the persisted skill_manage steps (a finished step has no status)."""
    return [
        batch_id
        for step in persisted_skill_steps(client, backend_url, chat_id)
        if step.get("status") not in FAILED_STATUSES
        and isinstance(batch_id := step.get("skill_mutation_batch_id"), str)
        and batch_id
    ]


def catalog_skill_id(client: httpx.Client, backend_url: str, name: str) -> str | None:
    listing = client.get(f"{backend_url}/api/v1/skills/", timeout=30.0)
    listing.raise_for_status()
    for skill in listing.json().get("skills") or []:
        if isinstance(skill, dict) and skill.get("name") == name:
            return str(skill["id"])
    return None


def wait_for[T](check: Callable[[], T], *, timeout_sec: float, what: str) -> T:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(2.0)
    pytest.fail(f"timed out after {timeout_sec:.0f}s waiting for {what}")
