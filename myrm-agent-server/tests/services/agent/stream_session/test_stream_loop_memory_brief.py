"""Tests for memory brief SSE prelude in stream_loop."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    iter_agent_stream_chunks,
)


def _make_session(
    *,
    include_preview: bool = True,
    brief_status: dict[str, str] | None = None,
) -> MagicMock:
    session = MagicMock()
    session.request.chat_id = "chat-1"
    session.request.action_mode = "general"
    session.request.use_workflow = False
    session.request.blueprint_id = None
    session.request.mention_references = None
    session.request.resume_value = None
    session.request.ephemeral_subagents = None
    session.routing_tier = "complex"
    session.params.message_id = "msg-1"
    session.cancel_token.is_cancelled = False
    session.goal_provider = None
    session.collector = MagicMock()
    session.collector.content = ""
    extra_context: dict[str, object] = {}
    if include_preview:
        extra_context["memory_brief_preview"] = {
            "snapshot_id": "snap-123",
            "generated_at_ms": 12345,
            "namespaces": ["global", "agent:default"],
            "is_cold_start": False,
            "stable": {
                "working_state": False,
                "profile_keys": ["language"],
                "instruction_count": 1,
                "rule_count": 2,
            },
            "learned": {
                "preference_count": 2,
                "rule_count": 1,
                "correction_count": 0,
                "preference_ids": ["mem-p1"],
                "rule_ids": ["mem-r1"],
            },
        }
    if brief_status is not None:
        extra_context["memory_brief_status"] = brief_status
    elif include_preview:
        extra_context["memory_brief_status"] = {"state": "ready"}
    session.extra_context = extra_context
    return session


def _parse_sse_chunk(chunk: str) -> dict[str, object]:
    assert chunk.startswith("data: ")
    payload = chunk[len("data: ") :].strip()
    return json.loads(payload)


class TestMemoryBriefPrelude:
    @pytest.mark.asyncio
    async def test_emit_memory_brief_before_stream_and_attach_snapshot_id(self) -> None:
        session = _make_session()
        approval = ApprovalTimeoutHolder()

        async def _fake_stream(*_args, **_kwargs):
            yield {"type": "message_end"}

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch(
                "app.services.agent.stream_session.stream_loop.should_suggest_workflow_for_session",
                return_value=False,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
                return_value={"used": 20, "total": 200},
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
                return_value={"state": "applied", "source": "snapshot"},
            ),
            patch(
                "app.services.agent.stream_session.stream_loop.enqueue_memory_brief_status_telemetry"
            ) as mock_enqueue_status_telemetry,
        ):
            chunks: list[str] = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                chunks.append(chunk)

        assert chunks, "expected at least memory_brief and message_end chunks"
        first_event = _parse_sse_chunk(chunks[0])
        assert first_event.get("type") == "memory_brief"
        assert first_event.get("messageId") == "msg-1"

        message_end_event = next(
            _parse_sse_chunk(chunk) for chunk in chunks if '"type":"message_end"' in chunk
        )
        assert message_end_event.get("memory_brief_snapshot_id") == "snap-123"
        assert message_end_event.get("memory_brief_status") == {
            "state": "ready",
            "injection": {"state": "applied", "source": "snapshot"},
        }
        mock_enqueue_status_telemetry.assert_called_once_with(
            phase="stream",
            payload={"state": "ready", "injection": {"state": "applied", "source": "snapshot"}},
        )

    @pytest.mark.asyncio
    async def test_attach_skipped_status_when_brief_preview_missing(self) -> None:
        session = _make_session(
            include_preview=False,
            brief_status={"state": "skipped", "reason": "timeout"},
        )
        approval = ApprovalTimeoutHolder()

        async def _fake_stream(*_args, **_kwargs):
            yield {"type": "message_end"}

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch(
                "app.services.agent.stream_session.stream_loop.should_suggest_workflow_for_session",
                return_value=False,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
                return_value={"used": 12, "total": 256},
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
                return_value={"state": "applied", "source": "fallback"},
            ),
        ):
            chunks: list[str] = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                chunks.append(chunk)

        assert all('"type":"memory_brief"' not in chunk for chunk in chunks)
        message_end_event = next(
            _parse_sse_chunk(chunk) for chunk in chunks if '"type":"message_end"' in chunk
        )
        assert message_end_event.get("memory_brief_status") == {
            "state": "skipped",
            "source": "preflight",
            "reason": "timeout",
            "injection": {"state": "applied", "source": "fallback"},
        }

    @pytest.mark.asyncio
    async def test_skip_invalid_memory_budget_payload(self) -> None:
        session = _make_session()
        approval = ApprovalTimeoutHolder()

        async def _fake_stream(*_args, **_kwargs):
            yield {"type": "message_end"}

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch(
                "app.services.agent.stream_session.stream_loop.should_suggest_workflow_for_session",
                return_value=False,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
                return_value=None,
            ),
        ):
            chunks: list[str] = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                chunks.append(chunk)

        message_end_event = next(
            _parse_sse_chunk(chunk) for chunk in chunks if '"type":"message_end"' in chunk
        )
        assert "memoryBudget" not in message_end_event
        assert message_end_event.get("memory_brief_status") == {"state": "ready"}

    @pytest.mark.asyncio
    async def test_attach_not_applied_injection_reason(self) -> None:
        session = _make_session(include_preview=False, brief_status={"state": "skipped", "reason": "timeout"})
        approval = ApprovalTimeoutHolder()

        async def _fake_stream(*_args, **_kwargs):
            yield {"type": "message_end"}

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch(
                "app.services.agent.stream_session.stream_loop.should_suggest_workflow_for_session",
                return_value=False,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
                return_value={"used": 8, "total": 64},
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
                return_value={"state": "not_applied", "reason": "already_present"},
            ),
        ):
            chunks: list[str] = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                chunks.append(chunk)

        message_end_event = next(
            _parse_sse_chunk(chunk) for chunk in chunks if '"type":"message_end"' in chunk
        )
        assert message_end_event.get("memory_brief_status") == {
            "state": "skipped",
            "source": "preflight",
            "reason": "timeout",
            "injection": {"state": "not_applied", "reason": "already_present"},
        }

    @pytest.mark.asyncio
    async def test_skip_memory_brief_in_resume_mode(self) -> None:
        session = _make_session()
        session.request.resume_value = {"decision": "approve"}
        approval = ApprovalTimeoutHolder()

        async def _fake_stream(*_args, **_kwargs):
            yield {"type": "message_end"}

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch(
                "app.services.agent.stream_session.stream_loop.should_suggest_workflow_for_session",
                return_value=False,
            ),
        ):
            chunks: list[str] = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                chunks.append(chunk)

        assert all('"type":"memory_brief"' not in chunk for chunk in chunks)

    @pytest.mark.asyncio
    async def test_resume_mode_still_emits_injection_status_when_brief_status_missing(self) -> None:
        session = _make_session(include_preview=False, brief_status=None)
        session.request.resume_value = {"decision": "approve"}
        approval = ApprovalTimeoutHolder()

        async def _fake_stream(*_args, **_kwargs):
            yield {"type": "message_end"}

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch(
                "app.services.agent.stream_session.stream_loop.should_suggest_workflow_for_session",
                return_value=False,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
                return_value={"used": 6, "total": 60},
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
                return_value={"state": "not_applied", "reason": "missing_context"},
            ),
        ):
            chunks: list[str] = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                chunks.append(chunk)

        message_end_event = next(
            _parse_sse_chunk(chunk) for chunk in chunks if '"type":"message_end"' in chunk
        )
        assert message_end_event.get("memoryBudget") == {"used": 6, "total": 60}
        assert message_end_event.get("memory_brief_status") == {
            "state": "skipped",
            "source": "runtime_fallback",
            "injection": {"state": "not_applied", "reason": "missing_context"},
        }

