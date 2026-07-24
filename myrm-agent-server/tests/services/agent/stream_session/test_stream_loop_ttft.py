from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
    _capture_stream_ttft_if_needed,
    iter_agent_stream_chunks,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def _build_session(*, started_at: float) -> SimpleNamespace:
    return SimpleNamespace(
        stream_ttft_ms=None,
        stream_started_at_monotonic=started_at,
        params=SimpleNamespace(message_id="msg-ttft-1"),
    )


def test_capture_stream_ttft_from_message_chunk(monkeypatch) -> None:
    session = _build_session(started_at=100.0)
    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_loop.time.perf_counter",
        lambda: 100.251,
    )

    _capture_stream_ttft_if_needed(
        session=session,
        chunk={"type": "message", "data": "hello"},
    )
    assert session.stream_ttft_ms == 251

    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_loop.time.perf_counter",
        lambda: 101.0,
    )
    _capture_stream_ttft_if_needed(
        session=session,
        chunk={"type": "message", "data": "later token"},
    )
    assert session.stream_ttft_ms == 251


def test_capture_stream_ttft_accepts_reasoning_dict_payload(monkeypatch) -> None:
    session = _build_session(started_at=10.0)
    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_loop.time.perf_counter",
        lambda: 10.5,
    )

    _capture_stream_ttft_if_needed(
        session=session,
        chunk={"type": "reasoning", "data": {"content": "thinking"}},
    )
    assert session.stream_ttft_ms == 500


def test_capture_stream_ttft_accepts_structured_payload(monkeypatch) -> None:
    session = _build_session(started_at=20.0)
    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_loop.time.perf_counter",
        lambda: 20.5,
    )

    _capture_stream_ttft_if_needed(
        session=session,
        chunk={"type": "message", "data": {"content": [{"text": "chunk text"}]}},
    )
    assert session.stream_ttft_ms == 500


def test_capture_stream_ttft_ignores_empty_or_non_visible_payload(monkeypatch) -> None:
    session = _build_session(started_at=1.0)
    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_loop.time.perf_counter",
        lambda: 2.0,
    )

    _capture_stream_ttft_if_needed(
        session=session,
        chunk={"type": "message", "data": ""},
    )
    _capture_stream_ttft_if_needed(
        session=session,
        chunk={"type": "reasoning", "data": {}},
    )
    _capture_stream_ttft_if_needed(
        session=session,
        chunk={"type": "status", "data": {"phase": "waiting"}},
    )
    assert session.stream_ttft_ms is None


@pytest.mark.asyncio
async def test_iter_stream_injects_ttft_into_message_end(monkeypatch) -> None:
    async def _fake_fast_lane_stream(*_args, **_kwargs):
        yield {"type": "message", "data": "hello"}
        yield {"type": "message_end", "usage": {"total_tokens": 1}}

    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_loop.create_fast_lane_stream",
        lambda *_args, **_kwargs: _fake_fast_lane_stream(),
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.stream_loop.time.perf_counter",
        lambda: 100.2,
    )

    session = SimpleNamespace(
        request=SimpleNamespace(
            resume_value=None,
            action_mode="fast",
            use_workflow=False,
            blueprint_id=None,
            mention_references=None,
            ephemeral_subagents=None,
            chat_id=None,
        ),
        params=SimpleNamespace(message_id="msg-e2e-ttft", query="hi"),
        cancel_token=SimpleNamespace(
            is_cancelled=False,
            cancel_reason=None,
            cancel=lambda *_args, **_kwargs: None,
        ),
        steering_token=None,
        routing_tier="simple",
        collector=StreamContentCollector(chat_id=None),
        goal_provider=None,
        extra_context={},
        stream_started_at_monotonic=100.0,
        stream_ttft_ms=None,
    )
    approval = ApprovalTimeoutHolder()
    clarification = ClarificationTimeoutHolder()

    chunks = [chunk async for chunk in iter_agent_stream_chunks(session, approval, clarification)]
    message_end_chunk = next(
        chunk for chunk in chunks if '"type":"message_end"' in chunk or '"type": "message_end"' in chunk
    )
    payload = json.loads(message_end_chunk[len("data: ") :].strip())
    assert payload["stream_ttft_ms"] == 200

