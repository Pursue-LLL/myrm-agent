"""Live E2E: per-agent ``max_iterations`` must translate into the harness recursion
budget and surface an ``iteration_limit_reached`` stop reason in real agent-stream.

The full chain under test (no mocks on the agent path):
frontend config -> AgentCreate.max_iterations -> DB -> converter
(``resolved.max_iterations``) -> AgentRuntimeSpec -> ``recursion_limit * 2``
-> LangGraph recursion budget -> ``iteration_limit_reached`` SSE event.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import get_model_selection

_ITERATION_QUERY = (
    "Follow this EXACT multi-step task using ONLY the bash tool, one call at a time: "
    "echo 1, then echo 2, then echo 3, then echo 4, then echo 5, then echo 6, then echo 7, "
    "then echo 8. After all eight calls succeed, reply with the single word DONE."
)


def _create_agent(client: TestClient, *, name: str, max_iterations: int | None) -> str:
    payload: dict[str, object] = {"name": name}
    if max_iterations is not None:
        payload["max_iterations"] = max_iterations
    resp = client.post("/api/agents", json=payload)
    assert resp.status_code == 200, resp.text
    data = (resp.json().get("data") or {})
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _limit_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [e for e in events if e.get("type") == "iteration_limit_reached"]


def _error_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [e for e in events if isinstance(e, dict) and e.get("type") == "error"]


@pytest.mark.integration
def test_create_agent_rejects_max_iterations_below_min(client: TestClient) -> None:
    """Boundary: the AgentCreate schema clamps max_iterations to [5, 500]."""
    resp = client.post("/api/agents", json={"name": "clamp-boundary", "max_iterations": 4})
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
def test_create_agent_rejects_max_iterations_above_max(client: TestClient) -> None:
    """Boundary: max_iterations=501 must be rejected by the schema."""
    resp = client.post("/api/agents", json={"name": "clamp-boundary", "max_iterations": 501})
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
def test_create_agent_accepts_max_iterations_at_max(client: TestClient) -> None:
    """Boundary: max_iterations=500 is the legal upper bound and persists."""
    name = f"clamp-max-{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/agents", json={"name": name, "max_iterations": 500})
    assert resp.status_code == 200, resp.text
    data = (resp.json().get("data") or {})
    assert data.get("max_iterations") == 500
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_max_iterations_caps_recursion_budget_live(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """A small max_iterations must stop the real agent at the recursion budget
    with an iteration_limit_reached event instead of a hard error."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    agent_id = _create_agent(
        client, name=f"lim-{uuid.uuid4().hex[:8]}", max_iterations=5
    )
    chat_id = f"test_lim_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert resp.status_code == 200

    events: list[dict[str, object]] = []
    for _attempt in range(2):
        payload: dict[str, object] = {
            "messageId": f"msg_{uuid.uuid4().hex[:8]}",
            "chatId": chat_id,
            "query": _ITERATION_QUERY,
            "modelSelection": get_model_selection(),
            "actionMode": "agent",
            "enableMemory": False,
            "agentId": agent_id,
        }
        events = _collect_agent_stream(client, payload, stream_timeout=240.0)
        if _limit_events(events):
            break

    limit_events = _limit_events(events)
    assert limit_events, (
        "expected iteration_limit_reached for max_iterations=5; event types="
        f"{sorted({e.get('type') for e in events if isinstance(e.get('type'), str)})}"
    )
    assert not _error_events(events), (
        f"unexpected error events: {_error_events(events)[:2]}"
    )


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_default_max_iterations_completes_normally(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """Without a configured max_iterations the agent runs the default budget and
    finishes a simple turn normally (no iteration limit, no error)."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    agent_id = _create_agent(
        client, name=f"def-{uuid.uuid4().hex[:8]}", max_iterations=None
    )
    chat_id = f"test_def_{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert resp.status_code == 200

    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "Reply with exactly: OK",
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        "agentId": agent_id,
    }
    events = _collect_agent_stream(client, payload, stream_timeout=240.0)

    assert not _limit_events(events), (
        "default max_iterations must not hit the iteration limit on a simple turn"
    )
    assert not _error_events(events), (
        f"unexpected error events: {_error_events(events)[:2]}"
    )
    got_reply = any(
        isinstance(e.get("type"), str)
        and e["type"] == "message"
        and isinstance(e.get("data"), str)
        and e["data"].strip()
        for e in events
    )
    assert got_reply, "expected a message event with content for a simple turn"


def _put_max_iterations(
    client: TestClient, value: int | str | None
):
    """Create a fresh agent then PUT a max_iterations value onto it."""
    agent_id = _create_agent(client, name=f"put-{uuid.uuid4().hex[:8]}", max_iterations=None)
    payload: dict[str, object] = {"max_iterations": value}
    return client.put(f"/api/agents/{agent_id}", json=payload)


@pytest.mark.integration
def test_update_agent_rejects_max_iterations_below_min(client: TestClient) -> None:
    """PUT must enforce the same [5, 500] bounds as POST."""
    resp = _put_max_iterations(client, 4)
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
def test_update_agent_rejects_max_iterations_above_max(client: TestClient) -> None:
    """Boundary: max_iterations=501 rejected on PUT too."""
    resp = _put_max_iterations(client, 501)
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
def test_update_agent_rejects_non_integer_max_iterations(client: TestClient) -> None:
    """A non-integer value must fail Pydantic int coercion on PUT."""
    resp = _put_max_iterations(client, "abc")
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
def test_update_agent_accepts_max_iterations_at_max(client: TestClient) -> None:
    """PUT max_iterations=500 is the legal upper bound and must persist."""
    resp = _put_max_iterations(client, 500)
    assert resp.status_code == 200, resp.text
    assert (resp.json().get("data") or {}).get("max_iterations") == 500


@pytest.mark.integration
def test_update_agent_explicit_null_resets_to_default(client: TestClient) -> None:
    """Clearing the field in the UI sends explicit null; that must reset the
    stored value back to the system default (DB NULL), not be ignored."""
    agent_id = _create_agent(client, name=f"reset-{uuid.uuid4().hex[:8]}", max_iterations=50)
    resp = client.put(f"/api/agents/{agent_id}", json={"max_iterations": None})
    assert resp.status_code == 200, resp.text
    data = (resp.json().get("data") or {})
    assert data.get("max_iterations") is None, (
        f"explicit null must reset to default, got {data.get('max_iterations')}"
    )


@pytest.mark.integration
def test_update_agent_omitted_field_keeps_existing(client: TestClient) -> None:
    """A partial PUT that omits max_iterations must leave the stored value
    untouched (standard no-op semantics for non-sent fields)."""
    agent_id = _create_agent(client, name=f"keep-{uuid.uuid4().hex[:8]}", max_iterations=50)
    resp = client.put(f"/api/agents/{agent_id}", json={"description": "only desc"})
    assert resp.status_code == 200, resp.text
    data = (resp.json().get("data") or {})
    assert data.get("max_iterations") == 50, (
        f"omitted max_iterations must be preserved, got {data.get('max_iterations')}"
    )


@pytest.mark.integration
def test_update_agent_rejects_built_in_agent(client: TestClient) -> None:
    """Built-in agents are read-only: PUT must reject with 403 even when the
    payload is a legitimate max_iterations change."""
    import asyncio

    from sqlalchemy import update

    from app.database.connection import get_session
    from app.database.models.agent import Agent

    agent_id = _create_agent(client, name=f"bi-{uuid.uuid4().hex[:8]}", max_iterations=None)

    async def _mark_built_in() -> None:
        async with get_session() as session:
            await session.execute(
                update(Agent).where(Agent.id == agent_id).values(is_built_in=True)
            )
            await session.commit()

    asyncio.run(_mark_built_in())

    resp = client.put(f"/api/agents/{agent_id}", json={"max_iterations": 50})
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
def test_create_agent_ignores_unknown_camelcase_field(client: TestClient) -> None:
    """The frontend always sends snake_case ``max_iterations``. A camelCase
    ``maxIterations`` payload key is an *unknown* field today and must be
    silently ignored — locking the contract so a future Pydantic
    ``populate_by_name`` switch cannot silently change behavior."""
    resp = client.post(
        "/api/agents",
        json={"name": "camel-case-guard", "maxIterations": 50},
    )
    assert resp.status_code == 200, resp.text
    data = (resp.json().get("data") or {})
    assert data.get("max_iterations") is None, (
        f"camelCase maxIterations must be ignored, got {data.get('max_iterations')}"
    )
