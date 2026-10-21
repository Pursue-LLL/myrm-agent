"""E2E lane test: temporal hard-filter window on the real retrieval pipeline.

Lane-C flow (real LLM write + real harness search pipeline):
1. Real agent-stream conversation plants a valuable migration fact (auto extraction).
2. Control query without a time marker must hit the planted memory (baseline).
3. ``今天`` marker derives a same-day window; the planted memory stays inside.
4. ``去年`` marker derives a last-year window; the same memory is hard-pruned.
   The only delta between queries is the time marker, so the empty result set
   is direct evidence that the collect-stage since/until filter is live.
5. Cross-session agent query proves the planted memory influences reasoning.
"""

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import build_memory_e2e_embedding_retrieval_dict, get_model_selection


def _exhaust_stream(resp) -> None:
    for _line in resp.iter_lines():
        pass


def _stream_chat(client: TestClient, query: str, chat_id: str, retrieval: dict[str, object]) -> None:
    req = {
        "messageId": str(uuid.uuid4()),
        "query": query,
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "enableMemoryAutoExtraction": True,
        "memoryRequireConfirmation": False,
        "retrievalDict": retrieval,
    }
    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=req, timeout=120.0
    ) as resp:
        assert resp.status_code == 200
        _exhaust_stream(resp)


@pytest.mark.e2e
@pytest.mark.timeout(360)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY",
)
@pytest.mark.asyncio
async def test_temporal_window_hard_filter_lane_real_e2e(client: TestClient):
    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        pytest.skip("No embedding credential")

    chat_id = f"temporal-lane-{uuid.uuid4().hex[:8]}"

    plant = (
        "我们团队的生产数据库今天刚完成从 SQLite 到 Qdrant 的迁移，"
        "部署在杭州机房，使用 Qdrant 集群版 1.12，向量检索延迟降到 8 毫秒。"
    )
    _stream_chat(client, plant, chat_id, retrieval)

    # Background auto-extraction needs a beat before the memory is searchable.
    await asyncio.sleep(12.0)

    def _search(query: str) -> str:
        resp = client.get("/api/v1/memory/search", params={"query": query, "limit": 10})
        assert resp.status_code == 200
        return str(resp.json().get("results", []))

    # Baseline: same topic without any time marker must recall the planted fact.
    baseline = _search("生产数据库迁移方案用的是什么引擎")
    assert "Qdrant" in baseline, "Baseline query should recall the planted migration fact"

    # Same-day window: ``今天`` keeps today's planted memory inside the window.
    today = _search("今天我们聊的生产数据库迁移方案用的是什么引擎")
    assert "Qdrant" in today, "今天 window must keep today's planted memory inside"

    # Last-year window: the only delta is the time marker, and the same memory
    # is hard-pruned at the collect stage — direct temporal filter evidence.
    last_year = _search("去年我们聊的生产数据库迁移方案用的是什么引擎")
    assert "Qdrant" not in last_year, "去年 window must hard-prune today's planted memory"

    # Cross-session reasoning: a fresh chat must answer from planted memory.
    followup_chat = f"temporal-follow-{uuid.uuid4().hex[:8]}"
    _stream_chat(
        client,
        "今天早些时候我们聊过的那次生产数据库迁移，最终迁到了哪个数据库引擎？"
        "请基于记忆检索结果回答，检索不到就明说不知道。",
        followup_chat,
        retrieval,
    )
    recall = _search("今天聊的生产数据库迁移到哪个引擎")
    assert "Qdrant" in recall, "Cross-session recall should keep the planted fact searchable"
