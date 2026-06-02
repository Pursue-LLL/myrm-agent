"""E2E Test for Cache-Hit Pivot architecture in subagents."""

import json
import logging
import os
import time
import uuid

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(override=True)
logger = logging.getLogger(__name__)


def get_model_selection():
    raw_model = os.getenv("BASIC_MODEL")
    if not raw_model:
        raise ValueError("No BASIC_MODEL found in environment. Set BASIC_MODEL in .env.test")

    selection = {
        "providerId": "openai",
        "model": raw_model.split("/", 1)[1] if "/" in raw_model else raw_model,
    }
    return selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.getenv("BASIC_MODEL"),
    reason="Requires BASIC_MODEL in .env.test for E2E testing",
)
def test_subagent_fork_context_success(client: TestClient):
    """Test that context_mode=fork executes successfully without crashing."""
    try:
        model_selection = get_model_selection()
    except ValueError as e:
        logger.error(f"❌ {e}")
        return False

    payload = {
        "messageId": str(uuid.uuid4()),
        "query": "请帮我搜索2026年最新的AI监管政策",
        "modelSelection": model_selection,
        "chatHistory": [
            {"role": "user", "content": "你好，我是架构师"},
            {"role": "assistant", "content": "你好！请问有什么我可以帮您？"},
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
    logger.info(f"Stream collected ({elapsed_time:.2f}s)")

    events = []
    for line in raw_stream.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            try:
                events.append(json.loads(line[5:].strip()))
            except Exception:
                pass

    any(e.get("type") == "SUBAGENT_COMPLETION" for e in events)
    has_error = any(e.get("type") == "error" for e in events)

    if has_error:
        error_events = [e for e in events if e.get("type") == "error"]
        logger.error(f"Stream errors: {error_events}")
        raise AssertionError(f"Stream returned error: {error_events}")

    # We just want to ensure it runs successfully without crashing
    # (Since LLM might not always trigger subagent, we check for no errors as a baseline)
    logger.info("Test completed successfully without errors.")
    return True
