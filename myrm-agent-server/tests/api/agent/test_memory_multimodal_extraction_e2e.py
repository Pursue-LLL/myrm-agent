"""E2E: post-turn memory extraction on a turn that carries an image.

A real agent-stream turn that carries a large screenshot must still distil the
facts of the conversation into memory. The extraction prompt is recorded on its
way to the real LLM: it must hold the words only, never the attachment bytes.
"""

import asyncio
import base64
import io
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

# Bound at collection time: this directory's autouse fixture replaces the module attribute with a no-op
# (extraction is off for every other test here), so the real function is only reachable through this import.
from myrm_agent_harness.api.hooks import auto_extract_memories as real_auto_extract_memories
from PIL import Image

from tests.api.agent.utils import build_memory_e2e_embedding_retrieval_dict, get_model_selection

_EXTRACTION_POLL_ATTEMPTS = 12
_EXTRACTION_POLL_INTERVAL_SEC = 3.0
_NO_TOOLS = "只用一句话确认，禁止调用任何工具。"
_FACT = f"我的项目强制要求使用 Python 3.14，绝对不能使用更老的版本。{_NO_TOOLS}"
_SCREENSHOT_TURN = f"这就对了，附上我项目配置的截图。{_NO_TOOLS}"


def _noise_jpeg_data_url() -> str:
    """A screenshot-sized payload (~300 KB base64) so any leak is unmistakable."""
    image = Image.effect_noise((600, 600), 255).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _send_turn(
    client: TestClient, chat_id: str, query: str | list[dict[str, object]], retrieval: dict
) -> list[dict[str, object]]:
    request = {
        "messageId": str(uuid.uuid4()),
        "query": query,
        "chatId": chat_id,
        "modelSelection": {**get_model_selection(), "supportsVision": True},
        "actionMode": "agent",
        "enableMemoryAutoExtraction": True,
        "memoryRequireConfirmation": False,
        "retrievalDict": retrieval,
    }
    events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request, timeout=180.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if isinstance(payload, dict):
                    events.append(payload)
    return events


@pytest.mark.e2e
@pytest.mark.timeout(480)
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E test requires BASIC_API_KEY")
@pytest.mark.asyncio
async def test_screenshot_turn_is_extracted_from_its_words_only(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        pytest.skip("No embedding credential")

    from myrm_agent_harness.agent._internals import memory_extraction

    monkeypatch.setattr(memory_extraction, "auto_extract_memories", real_auto_extract_memories)

    extraction_prompts: list[list[dict[str, str]]] = []
    build_messages = memory_extraction.build_extraction_messages

    def _record(*args: object, **kwargs: object) -> list[dict[str, str]]:
        messages = build_messages(*args, **kwargs)
        extraction_prompts.append(messages)
        return messages

    monkeypatch.setattr(memory_extraction, "build_extraction_messages", _record)

    persisted: list[tuple[list[str], int]] = []
    persist = memory_extraction.persist_extracted_memories

    async def _persist_recorder(memories: list[object], *args: object, **kwargs: object) -> int:
        stored_count = await persist(memories, *args, **kwargs)  # type: ignore[arg-type]
        persisted.append(([str(getattr(memory, "content", memory)) for memory in memories], stored_count))
        return stored_count

    monkeypatch.setattr(memory_extraction, "persist_extracted_memories", _persist_recorder)

    def _screenshot_prompt_seen() -> bool:
        return any(_SCREENSHOT_TURN in turn["content"] for prompt in extraction_prompts for turn in prompt)

    chat_id = f"mem-mm-{uuid.uuid4().hex[:8]}"
    data_url = _noise_jpeg_data_url()

    fact_events = _send_turn(client, chat_id, _FACT, retrieval)
    screenshot_events = _send_turn(
        client,
        chat_id,
        [
            {"type": "text", "text": _SCREENSHOT_TURN},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
        retrieval,
    )

    for events in (fact_events, screenshot_events):
        assert any(event.get("type") == "message" for event in events), json.dumps(events, ensure_ascii=False)[:1500]

    # Extraction runs as a fire-and-forget task after the stream closes; wait until it has persisted, not a fixed delay.
    for _ in range(_EXTRACTION_POLL_ATTEMPTS):
        if _screenshot_prompt_seen() and persisted:
            break
        await asyncio.sleep(_EXTRACTION_POLL_INTERVAL_SEC)

    prompt_text = json.dumps(extraction_prompts, ensure_ascii=False)
    assert _screenshot_prompt_seen(), f"Post-turn extraction never ran on the screenshot turn: {prompt_text[:600]}"
    assert "data:image" not in prompt_text
    assert data_url[60:120] not in prompt_text
    assert len(prompt_text) < len(data_url) // 4

    extracted = [content for contents, _ in persisted for content in contents]
    assert any("3.14" in content for content in extracted), f"The fact must survive extraction: {extracted}"
    assert sum(stored_count for _, stored_count in persisted) >= 1, f"Nothing was persisted: {persisted}"
    assert not any("base64" in content or "data:image" in content for content in extracted)
