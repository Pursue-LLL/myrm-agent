"""E2E: agent-stream with structured_clarify must emit clarification_required and resume."""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection


def _clarification_required_events(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
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


def _event_types(events: list[dict[str, object]]) -> list[str]:
    return sorted(
        {str(event.get("type")) for event in events if event.get("type") is not None}
    )


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
        "Before doing anything else, use ask_question_tool exactly once to ask which framework I should use. "
        'Use title "Framework choice", one question id "framework" prompt "Which AI framework should I use?", '
        'two options id "langchain" label "LangChain" and id "llamaindex" label "LlamaIndex", '
        "requires_confirmation false. "
        "Do not use bash, write_file, render_ui_tool, or any other tools. "
        "After you receive my answer, reply with a single line starting with DONE."
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
        with client.stream(
            "POST", "/api/v1/agents/agent-stream", json=initial_payload, timeout=180.0
        ) as response:
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
    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=resume_payload, timeout=180.0
    ) as response:
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
    assert (
        resume_events
    ), "Resume stream should return events after clarification answer"
    final_text = _message_text(resume_events)
    assert (
        "DONE" in final_text.upper() or "langchain" in final_text.lower()
    ), f"Expected completion after resume; final_text={final_text[:200]!r}"


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_agent_stream_structured_clarify_skip_empty_resume(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """Real agent-stream: empty resumeValue {} must resume like Skip (B-package fix)."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yolo_mode_enabled_at": time.time(),
    }

    query = (
        "CRITICAL: Your very first action MUST be a single ask_question_tool call — no text reply before it. "
        "You MUST call ask_question_tool exactly once before any other action. "
        'Use title "Pick stack". Ask one question with id "stack" and prompt '
        '"Which stack?" with two options: id "a" label "A", id "b" label "B". '
        "Set requires_confirmation to false. "
        "Do not use bash, write_file, render_ui_tool, or any other tools. "
        "If the user skips or gives no answer, reply with exactly: DONE-SKIPPED"
    )

    chat_id = ""
    initial_events: list[dict[str, object]] = []
    for _attempt in range(2):
        chat_id = f"test_clarify_skip_{uuid.uuid4().hex[:8]}"
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
        with client.stream(
            "POST", "/api/v1/agents/agent-stream", json=initial_payload, timeout=180.0
        ) as response:
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
        if _clarification_required_events(initial_events):
            break

    clarify_events = _clarification_required_events(initial_events)
    assert clarify_events, (
        "Expected clarification_required before skip resume; "
        f"event_types={_event_types(initial_events)}"
    )

    resume_payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "",
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {
            "enabledBuiltinTools": ["structured_clarify"],
        },
        "resumeValue": {},
    }
    resume_events: list[dict[str, object]] = []
    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=resume_payload, timeout=180.0
    ) as response:
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
    assert resume_events, "Skip resume stream should return events"
    resume_types = _event_types(resume_events)
    assert "error" not in resume_types, f"resume stream errored: {resume_types}"
    assert resume_types != [
        "clarification_required"
    ], f"resumeValue {{}} did not progress past clarify interrupt: {resume_types}"
    final_text = _message_text(resume_events)
    completed = (
        "DONE-SKIPPED" in final_text.upper()
        or "DONE" in final_text.upper()
        or "message_end" in resume_types
    )
    assert completed, (
        f"Expected agent to continue after empty resumeValue; "
        f"types={resume_types}, final_text={final_text[:300]!r}"
    )
