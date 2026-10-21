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
from PIL import Image

from tests.api.agent.utils import build_memory_e2e_embedding_retrieval_dict, get_model_selection
from tests.support.memory_extraction_probe import ExtractionProbe, install_real_extraction_probe

_EXTRACTION_POLL_ATTEMPTS = 40
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
    client: TestClient, chat_id: str, query: str | list[dict[str, object]], retrieval: dict[str, object]
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


async def _wait_until_persisted(probe: ExtractionProbe) -> None:
    """Extraction runs as a fire-and-forget task after the stream closes: wait for it, not a fixed delay."""
    for _ in range(_EXTRACTION_POLL_ATTEMPTS):
        if probe.saw_prompt_containing(_SCREENSHOT_TURN) and probe.persisted:
            return
        await asyncio.sleep(_EXTRACTION_POLL_INTERVAL_SEC)


@pytest.mark.e2e
@pytest.mark.timeout(480)
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E test requires BASIC_API_KEY")
@pytest.mark.asyncio
async def test_screenshot_turn_is_extracted_from_its_words_only(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        pytest.skip("No embedding credential")

    probe = install_real_extraction_probe(monkeypatch)
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

    await _wait_until_persisted(probe)

    prompt_text = probe.prompt_text()
    assert probe.saw_prompt_containing(_SCREENSHOT_TURN), f"Extraction never ran on the screenshot turn: {probe.prompts}"
    assert "data:image" not in prompt_text
    assert data_url[60:120] not in prompt_text
    assert len(prompt_text) < len(data_url) // 4

    assert any("3.14" in content for content in probe.extracted_contents), probe.extracted_contents
    assert probe.stored_count >= 1, probe.persisted
    assert not any("base64" in content or "data:image" in content for content in probe.extracted_contents)
