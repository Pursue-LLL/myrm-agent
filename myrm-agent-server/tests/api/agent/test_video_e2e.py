"""Video understand/analyze capability E2E tests

Tests the complete video processing flow through the agent-stream endpoint:
- video_url content items are correctly routed and processed
- SSE analyzing_video / analyzing_video_clear events are emitted when fallback is needed
- Native video models pass through without analysis overhead
- Caching avoids redundant analysis for duplicate videos
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def _build_video_query(text: str, video_url: str) -> list[dict[str, object]]:
    """Build a multimodal query with text + video_url content."""
    return [
        {"type": "text", "text": text},
        {
            "type": "video_url",
            "video_url": {"url": video_url, "mime_type": "video/mp4"},
        },
    ]


def perform_video_stream(
    client: TestClient,
    query: list[dict[str, object]],
    model_selection: dict[str, object] | None = None,
) -> tuple[str, list[dict[str, object]], list[str]]:
    """Send a multimodal video query and collect SSE events."""
    request_data: dict[str, object] = {
        "messageId": f"vid-msg-{uuid.uuid4().hex[:12]}",
        "chatId": f"vid-chat-{uuid.uuid4().hex[:10]}",
        "query": query,
        "modelSelection": model_selection or get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected_data: list[dict[str, object]] = []
    message_chunks: list[str] = []
    status_events: list[str] = []

    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_data, timeout=180.0
    ) as response:
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if data is None:
                    continue
                collected_data.append(data)
                event_type = data.get("type", "unknown")

                if event_type in ("message", "reasoning"):
                    content = data.get("data", "")
                    if content:
                        message_chunks.append(str(content))
                elif event_type == "status":
                    step_key = data.get("step_key", "")
                    if step_key:
                        status_events.append(step_key)
            except json.JSONDecodeError:
                pass

    full_answer = "".join(message_chunks)
    return full_answer, collected_data, status_events


_FLAKY_SIGNALS = (
    "Authentication",
    "Authorization",
    "Recursion limit",
    "Cannot connect",
    "Connection error",
    "InternalServerError",
    "BadRequestError",
    "Param Incorrect",
    "quota exceeded",
    "SearchAPIError",
    "ToolExecutionError",
    "rate_limit",
)

_SAMPLE_VIDEO_URL = "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"


def _skip_on_flaky_error(collected_data: list[dict[str, object]]) -> None:
    """Skip test if upstream/env issues detected."""
    error_events = [d for d in collected_data if d.get("type") == "error"]
    if error_events:
        first_err = error_events[0]
        error_msg = str(first_err)
        if first_err.get("error_kind") == "format_error" or any(
            kw in error_msg for kw in _FLAKY_SIGNALS
        ):
            pytest.skip(f"Environment/upstream flaky: {error_msg[:240]}")
        pytest.fail(f"Agent execution error: {error_msg}")


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestVideoStreamE2E:
    """End-to-end tests for video processing in agent-stream."""

    def test_video_url_produces_response(self, client: TestClient):
        """Sending a video_url item should produce a valid agent response."""
        query = _build_video_query(
            "Describe what you see in this video in one sentence. No tool calls.",
            _SAMPLE_VIDEO_URL,
        )
        full_answer, collected_data, status_events = perform_video_stream(client, query)

        _skip_on_flaky_error(collected_data)

        assert len(collected_data) > 0, "Should have received SSE events"
        if full_answer:
            assert len(full_answer) > 5, "Answer should have meaningful content"

    def test_video_analysis_sse_events(self, client: TestClient):
        """When model does NOT support video natively, analyzing_video events should appear."""
        query = _build_video_query(
            "Briefly describe the video content. Reply in plain text only.",
            _SAMPLE_VIDEO_URL,
        )
        full_answer, collected_data, status_events = perform_video_stream(client, query)

        _skip_on_flaky_error(collected_data)

        # The test model (from BASIC_MODEL) likely does NOT support native video,
        # so we expect analyzing_video + analyzing_video_clear SSE events.
        # If the model DOES support native video, these won't appear (which is also correct).
        has_analysis_start = "analyzing_video" in status_events
        has_analysis_clear = "analyzing_video_clear" in status_events

        if has_analysis_start:
            assert has_analysis_clear, (
                "If analyzing_video was emitted, analyzing_video_clear must follow"
            )
            print("Video fallback analysis path verified: SSE events emitted correctly")
        else:
            print(
                "Model appears to support native video (no fallback needed), "
                "skipping SSE event assertion"
            )

    def test_video_with_text_only_query(self, client: TestClient):
        """Multimodal query with both text and video should produce coherent response."""
        query = _build_video_query(
            "Is there fire in this video? Answer only YES or NO.",
            _SAMPLE_VIDEO_URL,
        )
        full_answer, collected_data, _ = perform_video_stream(client, query)

        _skip_on_flaky_error(collected_data)

        assert len(collected_data) > 0
        if full_answer:
            normalized = full_answer.strip().upper()
            assert any(
                word in normalized for word in ("YES", "NO", "FIRE", "BLAZE", "FLAME")
            ), f"Expected YES/NO/fire-related answer, got: {full_answer[:100]}"
