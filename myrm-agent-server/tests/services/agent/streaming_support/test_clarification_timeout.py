"""Unit tests for Web clarification timeout scheduling."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.streaming_support.sse_helpers import (
    CLARIFICATION_NO_ANSWER_RESUME_VALUE,
    CLARIFICATION_TIMEOUT_SECONDS,
    extract_clarification_required,
    schedule_clarification_timeout,
)
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler


@pytest.fixture(autouse=True)
def _reset_scheduler() -> None:
    ApprovalTimeoutScheduler._instance = None


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


@pytest.mark.asyncio
async def test_schedule_clarification_timeout_registers_empty_resume_override() -> None:
    captured: dict[str, object] = {}

    def fake_schedule(
        key: str,
        timeout_seconds: float,
        behavior: str,
        resume_callback: object,
        *,
        resume_value_override: dict[str, object] | None = None,
    ) -> None:
        captured["key"] = key
        captured["timeout_seconds"] = timeout_seconds
        captured["override"] = resume_value_override
        captured["callback"] = resume_callback

    with patch.object(ApprovalTimeoutScheduler.get(), "schedule", side_effect=fake_schedule):
        schedule_clarification_timeout("chat-1", MagicMock(), timeout_seconds=12.0)

    assert captured["key"] == "chat-1"
    assert captured["timeout_seconds"] == 12.0
    assert captured["override"] == CLARIFICATION_NO_ANSWER_RESUME_VALUE
    assert callable(captured["callback"])


def test_clarification_timeout_default_is_900_seconds() -> None:
    assert CLARIFICATION_TIMEOUT_SECONDS == 900.0
