"""Unit tests for SSE event parsing helpers (interrupt and approval timeout detection)."""

from __future__ import annotations

import json

from app.services.agent.streaming_support.sse_helpers import (
    error_sse,
    extract_approval_timeout,
    extract_clarification_required,
    extract_directory_request_required,
)


def test_extract_clarification_required_true() -> None:
    event = {
        "type": "clarification_required",
        "data": {"type": "ask_question", "form": {"questions": []}},
    }
    chunk = f"data: {json.dumps(event)}\n\n"
    assert extract_clarification_required(chunk) is True


def test_extract_clarification_required_false_for_other_events() -> None:
    chunk = 'data: {"type":"message","data":"hello"}\n\n'
    assert extract_clarification_required(chunk) is False


def test_extract_clarification_required_false_for_malformed_json() -> None:
    assert extract_clarification_required("data: {broken}\n\n") is False


def test_extract_clarification_required_false_without_sse_prefix() -> None:
    assert extract_clarification_required('{"type":"clarification_required"}\n\n') is False


def test_error_sse_includes_message_id_when_provided() -> None:
    chunk = error_sse("boom", "msg-42")
    assert "msg-42" in chunk
    assert "boom" in chunk


def test_error_sse_generates_message_id_when_missing() -> None:
    chunk = error_sse("boom", None)
    assert "messageId" in chunk
    assert "boom" in chunk


def test_extract_approval_timeout_returns_none_for_wrong_event_type() -> None:
    chunk = 'data: {"type":"message","data":{}}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_non_dict_data() -> None:
    chunk = 'data: {"type":"tool_approval_request","data":"bad"}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_non_dict_extensions() -> None:
    chunk = 'data: {"type":"tool_approval_request","data":{"extensions":"bad"}}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_non_dict_timeout() -> None:
    chunk = 'data: {"type":"tool_approval_request","data":{"extensions":{"timeout":"bad"}}}\n\n'
    assert extract_approval_timeout(chunk) is None


def test_extract_approval_timeout_returns_none_for_malformed_json() -> None:
    assert extract_approval_timeout("data: tool_approval_request {broken}\n\n") is None


def test_extract_clarification_required_false_for_wrong_event_type() -> None:
    chunk = 'data: {"type":"message","clarification_required":true}\n\n'
    assert extract_clarification_required(chunk) is False


def test_extract_approval_timeout_parses_extensions() -> None:
    event = {
        "type": "tool_approval_request",
        "data": {
            "extensions": {"timeout": {"seconds": 120, "behavior": "allow"}},
        },
    }
    chunk = f"data: {json.dumps(event)}\n\n"
    parsed = extract_approval_timeout(chunk)
    assert parsed == {"seconds": 120, "behavior": "allow"}


def test_extract_approval_timeout_defaults_when_missing() -> None:
    event = {"type": "tool_approval_request", "data": {}}
    chunk = f"data: {json.dumps(event)}\n\n"
    parsed = extract_approval_timeout(chunk)
    assert parsed == {"seconds": 300, "behavior": "deny"}


def test_extract_approval_timeout_returns_none_for_invalid_payload() -> None:
    assert extract_approval_timeout("not sse") is None


def test_extract_directory_request_required_detects_sse_event() -> None:
    chunk = 'data: {"type":"directory_request_required","data":{"request":{}}}\n\n'
    assert extract_directory_request_required(chunk) is True


def test_extract_directory_request_required_rejects_unrelated_events() -> None:
    chunk = 'data: {"type":"message","data":""}\n\n'
    assert extract_directory_request_required(chunk) is False
