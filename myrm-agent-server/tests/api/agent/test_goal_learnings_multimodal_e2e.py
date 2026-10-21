"""E2E: goal-terminal learnings extraction on a goal turn that carries an image.

A real goal run whose user turn holds a large screenshot must still reach the learnings
extractor, and the transcript it hands to the real LLM must hold the words only.
"""

import asyncio
import base64
import io
import json
import os
import uuid
from collections.abc import Awaitable, Callable

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.core.features import init_features
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.memory.strategies import extractor
from myrm_agent_harness.toolkits.memory.strategies.extractor import ExtractedMemory
from PIL import Image

from app.services.features.registration import register_all_features
from tests.api.agent.test_goal_acceptance_e2e import _LocalBashExecutor
from tests.api.agent.utils import build_memory_e2e_embedding_retrieval_dict, check_e2e_errors, get_model_selection

_POLL_ATTEMPTS = 40
_POLL_INTERVAL_SEC = 3.0
_SCREENSHOT_NOTE = "附上我项目配置的截图，我们的项目强制要求使用 Python 3.14。"


def _noise_jpeg_data_url() -> str:
    image = Image.effect_noise((600, 600), 255).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _record_goal_learnings(
    monkeypatch: pytest.MonkeyPatch,
) -> list[list[dict[str, str]]]:
    """Run the real goal-learnings extraction, recording every transcript it receives."""
    transcripts: list[list[dict[str, str]]] = []
    real: Callable[..., Awaitable[list[ExtractedMemory]]] = extractor.extract_goal_learnings

    async def _recording(*args: object, **kwargs: object) -> list[ExtractedMemory]:
        messages = kwargs.get("messages")
        if isinstance(messages, list):
            transcripts.append(messages)
        return await real(*args, **kwargs)

    monkeypatch.setattr(extractor, "extract_goal_learnings", _recording)
    return transcripts


@pytest.mark.e2e
@pytest.mark.timeout(480)
@pytest.mark.skipif(not os.environ.get("BASIC_API_KEY"), reason="E2E test requires BASIC_API_KEY")
@pytest.mark.asyncio
async def test_goal_learnings_transcript_excludes_screenshot_bytes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    retrieval = build_memory_e2e_embedding_retrieval_dict()
    if retrieval is None:
        pytest.skip("No embedding credential")

    register_all_features()
    init_features(overrides={"goals_system": True})
    transcripts = _record_goal_learnings(monkeypatch)
    token = set_executor(_LocalBashExecutor())
    try:
        chat_id = f"goal-mm-{uuid.uuid4().hex[:8]}"
        assert client.post("/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200
        data_url = _noise_jpeg_data_url()

        request = {
            "messageId": str(uuid.uuid4()),
            "chatId": chat_id,
            "query": [
                {"type": "text", "text": f"{_SCREENSHOT_NOTE}不用做实际工作，直接调用 `complete_goal_tool` 完成目标即可。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
            "modelSelection": {**get_model_selection(), "supportsVision": True},
            "actionMode": "agent",
            "enableMemoryAutoExtraction": True,
            "memoryRequireConfirmation": False,
            "retrievalDict": retrieval,
            "goal": {
                "objective": "Record that the project requires Python 3.14",
                "maxTokens": 1000000,
                "acceptance_criteria": [{"type": "shell", "command": "echo ok", "timeout_seconds": 60}],
            },
        }
        events: list[dict[str, object]] = []
        with client.stream("POST", "/api/v1/agents/agent-stream", json=request, timeout=240.0) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if isinstance(payload, dict):
                        events.append(payload)
        check_e2e_errors(events)

        goal = client.get(f"/api/v1/goals/{chat_id}/status").json().get("goal")
        assert goal is not None and goal["status"] == "complete", goal

        # on_goal_terminal runs as a fire-and-forget task after the verdict: wait for it, not a fixed delay.
        for _ in range(_POLL_ATTEMPTS):
            if transcripts:
                break
            await asyncio.sleep(_POLL_INTERVAL_SEC)

        assert transcripts, "Goal learnings extraction never received a transcript"
        text = "\n".join(turn["content"] for transcript in transcripts for turn in transcript)
        assert _SCREENSHOT_NOTE in text, text[:500]
        assert "data:image" not in text
        assert data_url[60:120] not in text
        assert len(text) < len(data_url) // 4
    finally:
        reset_executor(token)
