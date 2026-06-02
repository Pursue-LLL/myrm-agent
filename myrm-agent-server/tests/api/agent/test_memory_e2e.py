"""Memory E2E test: verify that facts stored in one chat persist into another."""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import build_memory_e2e_embedding_retrieval_dict, get_model_selection


def _collect_stream_slices(resp) -> tuple[str, str]:
    """Return (final_message_text, all_relevant_text_concat) from SSE payloads.

    Collects message, reasoning, and tool_response content to capture the full
    agent output including tool-call results (e.g. memory recall responses).
    """
    message_parts: list[str] = []
    all_parts: list[str] = []
    saw_end = False
    for line in resp.iter_lines():
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        et = data.get("type")
        part = data.get("data") or ""
        if isinstance(part, str) and part and et in ("message", "reasoning", "tool_response"):
            all_parts.append(part)
        if isinstance(part, dict) and et == "tool_response":
            tool_text = json.dumps(part, ensure_ascii=False)
            all_parts.append(tool_text)
        if isinstance(part, str) and part and et == "message":
            message_parts.append(part)
        if et == "message_end":
            saw_end = True
        if et == "error":
            err = json.dumps(data, ensure_ascii=False)
            if any(
                s in err
                for s in (
                    "Authentication",
                    "BadRequestError",
                    "quota exceeded",
                    "SearchAPIError",
                )
            ):
                pytest.skip(f"Upstream/environment: {err[:400]}")
    if not saw_end:
        pytest.fail("SSE stream closed before message_end (incomplete agent run)")
    return "".join(message_parts), "".join(all_parts)


@pytest.mark.e2e
@pytest.mark.timeout(360)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_memory_e2e_real_world(client: TestClient):
    """Tell the agent a fact in chat-1, then verify via memory search API + optional second-chat SSE."""
    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        pytest.skip(
            "Memory E2E needs an embedding-capable credential: EMBEDDING_API_KEY / OPENAI_API_KEY / "
            "or BASIC_API_KEY (with optional EMBEDDING_BASE_URL/BASIC_BASE_URL for OpenAI-compatible gateways)"
        )

    chat_id_1 = f"mem-chat-{uuid.uuid4().hex[:8]}"
    chat_id_2 = f"mem-chat-{uuid.uuid4().hex[:8]}"

    fact = "我最喜欢的颜色是深海蓝，我有一只叫'奥利奥'的猫。"

    request_1 = {
        "messageId": str(uuid.uuid4()),
        "query": (
            f"请使用记忆工具把下面事实存入长期记忆（memory_save / memory_manage），不要只记在对话上下文里：{fact}"
        ),
        "chatId": chat_id_1,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": True,
        "retrievalDict": retrieval,
    }

    with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=request_1,
        timeout=240.0,
    ) as response_1:
        if response_1.status_code == 422:
            response_1.read()
            pytest.fail(f"Request validation error: {response_1.text}")
        assert response_1.status_code == 200
        _first_msgs, _first_all = _collect_stream_slices(response_1)
        assert isinstance(_first_msgs, str) and isinstance(_first_all, str)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 45.0
    search_ok = False
    while loop.time() < deadline:
        await asyncio.sleep(3.0)
        sr = client.get("/api/v1/memory/search", params={"query": "奥利奥 深海蓝 颜色", "limit": 10})
        if sr.status_code != 200:
            continue
        blob = json.dumps(sr.json(), ensure_ascii=False)
        if ("深海蓝" in blob or "蓝" in blob) and "奥利奥" in blob:
            search_ok = True
            break

    assert search_ok, (
        "Vector memory search did not return persisted fact markers within timeout "
        "(check embedding model BASIC_BASE_URL + EMBEDDING_MODEL compatibility)."
    )

    request_2 = {
        "messageId": str(uuid.uuid4()),
        "query": "我最喜欢的颜色是什么？我的猫叫什么名字？请直接简短回答事实。",
        "chatId": chat_id_2,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": True,
        "retrievalDict": retrieval,
    }

    with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=request_2,
        timeout=240.0,
    ) as response_2:
        assert response_2.status_code == 200
        _second_msgs, _second_all = _collect_stream_slices(response_2)

    assert isinstance(_second_msgs, str) and isinstance(_second_all, str)
    assert ("奥利奥" in _second_all and ("深海蓝" in _second_all or "蓝" in _second_all)), (
        "Expected streamed message or reasoning slices to contain recalled facts (cat name / color cues). "
        f"combined_stream_text={_second_all[:600]!r}"
    )
