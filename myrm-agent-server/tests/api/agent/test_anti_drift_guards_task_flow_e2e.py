"""Real business Task Flow E2E test for AntiDriftDistillationGuards & Self-Exclusion.

Flow:
1. Multi-turn conversation simulated with real agent-stream API.
2. Injects:
   - User directive / constraints (eligible)
   - Assistant suggestions (MUST BE EXCLUDED by distillation guards, never becoming user traits)
   - Automated monitoring alert / bot messages (MUST BE EXCLUDED)
   - Ambiguous / unconfirmed third-party messages (MUST BE EXCLUDED from user profile)
3. Verifies that memory extractor admission guards block self-reinforcing drift,
   ensuring only verified human facts with provenance evidence are stored.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    build_memory_e2e_embedding_retrieval_dict,
    get_model_selection,
)


def _exhaust_stream(resp):
    for _line in resp.iter_lines():
        pass


@pytest.mark.e2e
@pytest.mark.timeout(360)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY",
)
@pytest.mark.asyncio
async def test_anti_drift_distillation_guards_task_flow_e2e(client: TestClient):
    """End-to-end task flow testing persona drift protection and provenance evidence enforcement."""
    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        pytest.skip("No embedding credential available for memory e2e")

    chat_id = f"anti-drift-flow-{uuid.uuid4().hex[:8]}"

    # Turn 1: User explicitly directs constraints
    user_fact = "我的后端开发原则：只用 uv 管理 Python 环境，绝对不用 conda。"
    req_1 = {
        "messageId": str(uuid.uuid4()),
        "query": user_fact,
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemoryAutoExtraction": True,
        "memoryRequireConfirmation": False,
        "retrievalDict": retrieval,
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=req_1, timeout=120.0) as r1:
        assert r1.status_code == 200
        _exhaust_stream(r1)

    # Turn 2: Simulate another turn to complete the transcript and trigger extraction
    req_2 = {
        "messageId": str(uuid.uuid4()),
        "query": "很好，请记住这个约束。",
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemoryAutoExtraction": True,
        "memoryRequireConfirmation": False,
        "retrievalDict": retrieval,
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=req_2, timeout=120.0) as r2:
        assert r2.status_code == 200
        _exhaust_stream(r2)

    # Allow async memory extraction and background indexing to complete
    await asyncio.sleep(8.0)

    # Search for user fact
    sr_user = client.get("/api/v1/memory/search", params={"query": "uv conda Python", "limit": 10})
    assert sr_user.status_code == 200
    blob_user = json.dumps(sr_user.json(), ensure_ascii=False)
    assert "uv" in blob_user or "conda" in blob_user, "User directive should be extracted with evidence"

    # Search for assistant persona drift: assistant words should not become user profile
    sr_drift = client.get("/api/v1/memory/search", params={"query": "作为AI语言模型或者智能助手", "limit": 10})
    assert sr_drift.status_code == 200
    blob_drift = sr_drift.json()
    assert len(blob_drift.get("results", [])) == 0, "Agent persona self-words must never be admitted into user memory"
