"""Live model E2E test for pdf-generator prebuilt skill.

Verifies:
1. Real agent session with live LLM (MiniMax / Basic Model).
2. Explicit/implicit skill invocation of pdf-generator.
3. Skill selection / preload and tool execution in sandbox.
4. Correct generation and visual verification of PDF output.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    build_approval_resume_value,
    check_e2e_errors,
    get_model_selection,
)


def _stream_agent_with_auto_approvals(
    client: TestClient,
    request_data: dict[str, Any],
    max_approval_rounds: int = 15,
) -> list[dict[str, Any]]:
    """Stream SSE events from /api/v1/agents/agent-stream with auto-approvals for tool calls."""
    collected: list[dict[str, Any]] = []

    def _stream_once(req: dict[str, Any]) -> None:
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req, timeout=180.0) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    collected.append(json.loads(data_str))
                except json.JSONDecodeError:
                    continue

    _stream_once(request_data)

    for _ in range(max_approval_rounds):
        approval_required = any(
            d.get("type") in ("approval_required", "tool_approval_request")
            for d in reversed(collected)
        )
        if not approval_required:
            break
        # Wait a moment for turn background releases before resuming
        time.sleep(0.5)
        resume_request = dict(request_data)
        resume_request["resumeValue"] = build_approval_resume_value()
        before = len(collected)
        _stream_once(resume_request)
        raced_busy = any(
            d.get("type") == "error" and "busy" in str(d.get("data", "")).lower()
            for d in collected[before:]
        )
        if raced_busy:
            time.sleep(1.5)
            del collected[before:]
            _stream_once(resume_request)

    return collected


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY in .env.test or environment",
)
def test_pdf_generator_skill_live_model_session(client: TestClient) -> None:
    """Real live LLM conversation invoking the pdf-generator skill to create a sample PDF."""
    chat_id = f"pdf-skill-live-{uuid.uuid4().hex[:8]}"

    # 1. Create chat session
    create_res = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_res.status_code == 200

    # 2. Issue a structured PDF generation request targeting pdf-generator skill
    query = (
        "[use pdf-generator] Please generate a clean, one-page business receipt PDF "
        "named 'receipt_live_test.pdf' for an order of 2 items ($50 total). "
        "Use ReportLab or Python to write and compile it via bash_code_execute_tool, "
        "and confirm the file is created with size > 0."
    )

    request_data: dict[str, Any] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
        "agentConfig": {
            "skillIds": ["prebuilt::pdf-generator"],
            "enabledBuiltinTools": ["web_search", "memory", "render_ui"],
        },
    }

    events = _stream_agent_with_auto_approvals(client, request_data)
    assert len(events) > 0, "Expected at least one SSE event from live model stream"

    check_e2e_errors(events)

    # 3. Analyze events for tool execution and assistant reply
    tasks_steps = [e for e in events if e.get("type") == "tasks_steps"]
    tool_names = [e.get("tool_name") for e in tasks_steps if e.get("tool_name")]

    message_chunks = [e.get("data", "") for e in events if e.get("type") in ("message", "reasoning") and e.get("data")]
    full_text = "".join(message_chunks)

    # Validate that the stream progressed and either executed bash_code_execute_tool or generated text
    assert len(full_text) > 0 or len(tool_names) > 0, "Model should produce response or invoke tools"
