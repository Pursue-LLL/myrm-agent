"""E2E test for Memory Extractor No-Op Default and Signal Gate."""

import asyncio
import os
import uuid
from collections.abc import Iterable

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import build_memory_e2e_embedding_retrieval_dict, get_model_selection
from tests.support.memory_extraction_probe import install_real_extraction_probe


def _exhaust_stream(lines: Iterable[str]) -> None:
    for _line in lines:
        pass


@pytest.mark.e2e
@pytest.mark.timeout(360)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY",
)
@pytest.mark.asyncio
async def test_memory_extractor_noop_and_valuable_e2e(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = install_real_extraction_probe(monkeypatch)

    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        pytest.skip("No embedding credential")

    chat_id = f"mem-chat-{uuid.uuid4().hex[:8]}"

    # Send trivial message
    req_trivial = {
        "messageId": str(uuid.uuid4()),
        "query": "你好，今天天气不错啊，吃了吗？",
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemoryAutoExtraction": True,
        "memoryRequireConfirmation": False,
        "retrievalDict": retrieval,
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=req_trivial, timeout=120.0) as r1:
        assert r1.status_code == 200
        _exhaust_stream(r1.iter_lines())

    # Need at least 4 messages (2 turns) to bypass quality filter length check in some cases
    # We will just send a valuable constraint now.

    valuable_fact = "我的工作强制要求使用 Python 3.14 版本，绝对不能用更老的版本。"
    req_valuable = {
        "messageId": str(uuid.uuid4()),
        "query": valuable_fact,
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemoryAutoExtraction": True,
        "memoryRequireConfirmation": False,
        "retrievalDict": retrieval,
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=req_valuable, timeout=120.0) as r2:
        assert r2.status_code == 200
        _exhaust_stream(r2.iter_lines())

    req_trigger = {
        "messageId": str(uuid.uuid4()),
        "query": "这就对了",
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemoryAutoExtraction": True,
        "memoryRequireConfirmation": False,
        "retrievalDict": retrieval,
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=req_trigger, timeout=120.0) as r3:
        assert r3.status_code == 200
        _exhaust_stream(r3.iter_lines())

    # Wait for the fire-and-forget extraction of the valuable constraint to persist
    for _ in range(40):
        if any("3.14" in content for content in probe.extracted_contents):
            break
        await asyncio.sleep(3.0)

    # Inferred memories land in the review queue, so assert on what extraction produced rather than on search.
    extracted = probe.extracted_contents
    assert not any("天气" in content for content in extracted), "Trivial chat should be blocked by No-Op Default"
    assert any("3.14" in content for content in extracted), (
        f"Valuable constraint should have been extracted: {probe.persisted}; prompts={probe.prompts}"
    )
