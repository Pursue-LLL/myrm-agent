"""Live E2E: POOLED execution cache reuses BuiltExecutionUnit across two agent-stream turns."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.agent.execution_cache import (
    close_execution_cache_for_chat_all_agents,
    get_execution_cache,
)
from app.services.agent.execution_cache.fingerprint import build_execution_scope_key
from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_model_selection


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="Live E2E requires LITE_API_KEY or BASIC_API_KEY",
)
def test_live_execution_cache_reuses_unit_for_same_chat(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two agent-stream turns on one chat_id must create once then reuse the cache."""
    chat_id = f"test_exec_cache_{uuid.uuid4().hex[:8]}"
    scope_key = build_execution_scope_key(chat_id, "default")
    assert scope_key is not None

    asyncio.run(close_execution_cache_for_chat_all_agents(chat_id))

    caplog.set_level(logging.DEBUG, logger="app.services.agent.execution_cache.registry")

    for _turn in range(2):
        payload: dict[str, object] = {
            "query": "只回复 OK",
            "message_id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "action_mode": "agent",
            "model_selection": get_model_selection(),
            "timezone": "UTC",
            "enable_memory": False,
        }
        events = _collect_agent_stream(client, payload)
        check_e2e_errors(events)

    created = caplog.text.count("execution_cache_created")
    reused = caplog.text.count("execution_cache_reuse")
    assert created == 1, caplog.text
    assert reused >= 1, caplog.text
    assert scope_key in get_execution_cache()._entries

    asyncio.run(close_execution_cache_for_chat_all_agents(chat_id))
