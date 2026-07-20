"""E2E: agent-stream with structured_clarify must emit clarification_required and resume."""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection


def _clarification_required_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [event for event in events if event.get("type") == "clarification_required"]


def _message_text(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "message":
            continue
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
    return "".join(chunks)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_agent_stream_structured_clarify_interrupt_and_resume(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """Real agent-stream: ask_question_tool must emit clarification_required and complete after resume."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yolo_mode_enabled_at": time.time(),
    }

    query = (
        "CRITICAL: Your very first action MUST be a single ask_question_tool call — no text reply before it. "
        "You MUST call ask_question_tool exactly once before any other action. "
        'Use title "Framework choice". Ask one question with id "framework" and prompt '
        '"Which AI framework should I use?". Provide exactly two options: '
        'id "langchain" label "LangChain", id "llamaindex" label "LlamaIndex". '
        "Set requires_confirmation to false. "
        "Do not use bash, write_file, render_ui_tool, or any other tools. "
        "After you receive the user's answer, reply with a single line starting with DONE."
    )

    resume_answer = {"framework": "langchain"}

    initial_events: list[dict[str, object]] = []
    clarify_events: list[dict[str, object]] = []
    for _attempt in range(2):
        chat_id = f"test_clarify_{uuid.uuid4().hex[:8]}"
        message_id = f"msg_{uuid.uuid4().hex[:8]}"
        create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
        assert create_response.status_code == 200

        initial_payload: dict[str, object] = {
            "messageId": message_id,
            "chatId": chat_id,
            "query": query,
            "modelSelection": get_lite_model_selection(),
            "actionMode": "agent",
            "enableMemory": False,
            "agentConfig": {
                "enabledBuiltinTools": ["structured_clarify"],
            },
        }

        initial_events = []
        with client.stream("POST", "/api/v1/agents/agent-stream", json=initial_payload, timeout=180.0) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line or not line.strip().startswith("data: "):
                    continue
                raw = line.strip()[6:]
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    initial_events.append(data)

        check_e2e_errors(initial_events)
        clarify_events = _clarification_required_events(initial_events)
        if clarify_events:
            break

    assert clarify_events, (
        "Expected clarification_required after ask_question_tool (2 attempts); "
        f"event_types={sorted({e.get('type') for e in initial_events if isinstance(e.get('type'), str)})}"
    )

    clarify_data = clarify_events[0].get("data")
    assert isinstance(clarify_data, dict)
    assert clarify_data.get("type") == "ask_question"
    form = clarify_data.get("form")
    assert isinstance(form, dict)
    questions = form.get("questions")
    assert isinstance(questions, list) and len(questions) >= 1
    assert "requires_confirmation" in form
    assert form.get("requires_confirmation") is False
    resume_message_id = f"msg_{uuid.uuid4().hex[:8]}"
    resume_payload: dict[str, object] = {
        "messageId": resume_message_id,
        "chatId": chat_id,
        "query": "",
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {
            "enabledBuiltinTools": ["structured_clarify"],
        },
        "resumeValue": resume_answer,
    }
    resume_events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=resume_payload, timeout=180.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line or not line.strip().startswith("data: "):
                continue
            raw = line.strip()[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                resume_events.append(data)

    check_e2e_errors(resume_events)
    assert resume_events, "Resume stream should return events after clarification answer"
    final_text = _message_text(resume_events)
    assert "DONE" in final_text.upper() or "langchain" in final_text.lower(), (
        f"Expected completion after resume; final_text={final_text[:200]!r}"
    )