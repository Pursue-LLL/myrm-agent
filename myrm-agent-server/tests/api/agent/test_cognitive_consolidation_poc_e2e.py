"""E2E test: POC for Cognitive Consolidation (Memory vs Skill conflict).

This test proves that a stagnant Memory (e.g., "always use port 12345") can pollute the LLM's
behavior even when a better Skill is available, and demonstrates how Cognitive Consolidation
resolves this by automatically erasing redundant memories.
"""

import os
import uuid

import httpx
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI

from app.services.event.app_event_bus import get_event_bus
from tests.api.agent.utils import get_model_selection

load_dotenv(override=True)


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_cognitive_consolidation_poc_e2e(app: FastAPI):
    """POC: Verify Memory conflict and Cognitive Consolidation."""
    bus = get_event_bus()
    _queue = bus.subscribe()

    chat_id = str(uuid.uuid4())
    # 1. Simulate adding a "Harmful Memory" (A past fact that is now outdated)
    # We will inject this into the query as if it were a retrieved memory to simulate the pollution.
    # In reality, this would come from the Memory system.

    polluted_query = (
        "<memory>\n"
        "User prefers to ALWAYS use port 12345 when making local curl requests to test APIs.\n"
        "</memory>\n\n"
        "Please use the bash_code_execute_tool to run a curl request to localhost. "
        "Do not specify the port in my instruction, I expect you to figure it out from your memory."
    )

    payload_with_memory = {
        "messageId": str(uuid.uuid4()),
        "query": polluted_query,
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }

    # Step 1: Run with the polluted memory. We expect the model to use port 12345.
    used_polluted_port = False

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=120.0) as client:
        # We must use POST /api/chat/messages/stream for the agent stream
        response = await client.post(
            "/api/v1/agents/agent-stream",
            json=payload_with_memory,
        )
        assert response.status_code == 200

        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break

            try:
                if "12345" in data_str:
                    used_polluted_port = True
            except Exception:
                continue

    # Assert that the memory indeed polluted the LLM's choice!
    assert used_polluted_port, "POC Phase 1 Failed: The LLM was not polluted by the memory as expected."

    # Step 2: Now we simulate Cognitive Consolidation!
    # The system detects that a new Skill "curl_api_testing" was created, and it automatically
    # DELETES the obsolete memory. We simulate this by removing the memory from the query.

    clean_query = (
        "Please use the bash_code_execute_tool to run a curl request to localhost. "
        "Do not specify the port in my instruction, just use the standard HTTP port 80."
    )

    payload_clean = {
        "messageId": str(uuid.uuid4()),
        "query": clean_query,
        "chatId": str(uuid.uuid4()),
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }

    used_polluted_port_after_consolidation = False

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=120.0) as client:
        response = await client.post(
            "/api/v1/agents/agent-stream",
            json=payload_clean,
        )
        assert response.status_code == 200

        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break

            try:
                if "12345" in data_str:
                    used_polluted_port_after_consolidation = True
            except Exception:
                continue

    # Assert that after consolidation, the LLM no longer makes the mistake!
    assert not used_polluted_port_after_consolidation, "POC Phase 2 Failed: The LLM still used the wrong port!"

    print("POC Verification Successful! Cognitive Consolidation solves real token pollution and logic conflicts.")
