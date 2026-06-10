"""E2E Test for Cache-Hit Pivot architecture in subagents.

[POS]
Integration test for context_mode=fork subagent flow via agent-stream API.
"""

import json
import logging
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.getenv("BASIC_MODEL"),
    reason="Requires BASIC_MODEL in .env.test for E2E testing",
)
def test_subagent_fork_context_success(client: TestClient):
    """Test that context_mode=fork executes successfully without crashing."""
    model_selection = get_model_selection()

    payload = {
        "messageId": str(uuid.uuid4()),
        "query": "Say hello and introduce yourself briefly.",
        "modelSelection": model_selection,
        "chatHistory": [
            {"role": "user", "content": "Hi there"},
            {"role": "assistant", "content": "Hello! How can I help you?"},
        ],
        "agentConfig": {"ephemeralSubagents": {"search": {"context_mode": "fork", "system_prompt": "You are a web searcher"}}},
    }

    start_time = time.time()
    response = client.post(
        "/api/v1/agents/agent-stream",
        json=payload,
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    raw_stream = response.text
    elapsed_time = time.time() - start_time
    logger.info("Stream collected (%.2fs)", elapsed_time)

    events = []
    for line in raw_stream.split("\n"):
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        try:
            events.append(json.loads(line[5:].strip()))
        except Exception:
            pass

    has_error = any(e.get("type") == "error" for e in events)

    if has_error:
        error_events = [e for e in events if e.get("type") == "error"]
        logger.error("Stream errors: %s", error_events)
        raise AssertionError(f"Stream returned error: {error_events}")

    logger.info("Fork context test completed successfully without errors.")
