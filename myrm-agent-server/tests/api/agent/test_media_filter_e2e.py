"""E2E tests for proactive media filtering (Roadmap #17).

Exercises the real agent-stream pipeline with multimodal input and
verifies STATUS events reach the client.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_lite_model_selection, get_model_selection

# Minimal 1x1 red PNG
_TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _build_image_query(text: str) -> list[dict[str, object]]:
    return [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"},
        },
    ]


def _collect_stream(
    client: TestClient,
    query: list[dict[str, object]],
    model_selection: dict[str, object],
) -> tuple[list[str], list[dict[str, object]]]:
    request_data: dict[str, object] = {
        "messageId": f"media-msg-{uuid.uuid4().hex[:12]}",
        "chatId": f"media-chat-{uuid.uuid4().hex[:10]}",
        "query": query,
        "modelSelection": model_selection,
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    status_events: list[str] = []
    collected: list[dict[str, object]] = []

    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_data, timeout=180.0
    ) as response:
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if data is None:
                continue
            collected.append(data)
            if data.get("type") == "status":
                step_key = data.get("step_key", "")
                if step_key:
                    status_events.append(str(step_key))

    return status_events, collected


_FLAKY_SIGNALS = (
    "Authentication",
    "Authorization",
    "Cannot connect",
    "Connection error",
    "rate_limit",
    "quota exceeded",
)


def _skip_on_flaky(collected: list[dict[str, object]]) -> None:
    blob = json.dumps(collected)
    for sig in _FLAKY_SIGNALS:
        if sig in blob:
            pytest.skip(f"Upstream flaky: {sig}")


@pytest.mark.e2e
def test_proactive_media_stripped_when_vision_disabled(client: TestClient) -> None:
    """supportsVision=false + image -> media_stripped STATUS before LLM call."""
    selection = {**get_model_selection(), "supportsVision": False}
    status_events, collected = _collect_stream(
        client,
        _build_image_query(
            "E2E: reply with one word RED if you see red, else NOIMAGE."
        ),
        selection,
    )
    _skip_on_flaky(collected)
    assert (
        "media_stripped" in status_events
    ), f"Expected media_stripped in STATUS events, got: {status_events}"


@pytest.mark.e2e
def test_learner_triggers_strip_even_when_vision_flag_true(client: TestClient) -> None:
    """Runtime learner rejects_media forces proactive strip."""
    from myrm_agent_harness.toolkits.llms.capability_learner import (
        ModelCapabilityLearner,
        get_capability_learner,
    )

    ModelCapabilityLearner._instance = None
    selection = get_model_selection()
    model_name = str(selection["model"])
    get_capability_learner().learn(model_name, "rejects_media", True)

    selection_with_vision = {**selection, "supportsVision": True}
    status_events, collected = _collect_stream(
        client,
        _build_image_query("E2E learner: one word."),
        selection_with_vision,
    )
    _skip_on_flaky(collected)
    assert "media_stripped" in status_events


@pytest.mark.e2e
def test_text_only_query_never_emits_media_stripped(client: TestClient) -> None:
    selection = {**get_model_selection(), "supportsVision": False}
    status_events, collected = _collect_stream(
        client,
        [{"type": "text", "text": "E2E: reply OK only."}],
        selection,
    )
    _skip_on_flaky(collected)
    assert "media_stripped" not in status_events


@pytest.mark.e2e
def test_no_media_stripped_when_vision_enabled(client: TestClient) -> None:
    """Vision-capable model + supportsVision=true -> no proactive strip notification."""
    selection = {**get_lite_model_selection(), "supportsVision": True}
    status_events, collected = _collect_stream(
        client,
        _build_image_query("E2E: what color? one word only."),
        selection,
    )
    _skip_on_flaky(collected)
    assert (
        "media_stripped" not in status_events
    ), f"Unexpected media_stripped when vision enabled: {status_events}"
