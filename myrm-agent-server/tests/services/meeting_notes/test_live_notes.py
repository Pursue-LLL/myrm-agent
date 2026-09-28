"""Unit tests for the live (in-meeting) notes session."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.meeting_notes.live_notes import (  # noqa: E402
    LiveNotesRegistry,
    LiveNotesSession,
)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """Minimal async LLM stub returning a strict-JSON minutes payload."""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, _prompt: str) -> _FakeResponse:
        self.calls += 1
        await asyncio.sleep(0)
        return _FakeResponse(
            json.dumps(
                {
                    "title": "Live Sync",
                    "summary": "Discussed rollout.",
                    "decisions": ["Ship plan A"],
                    "debate_points": ["Timeline"],
                    "risks": ["Vendor lock-in"],
                    "action_items": [
                        {"description": "Draft spec", "owner": "Alice", "due_hint": "Fri"}
                    ],
                }
            )
        )


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_ingest_ignores_empty_and_counts_lines() -> None:
    session = LiveNotesSession("s1", clock=_Clock())
    assert session.ingest("   ") is False
    assert session.ingest("hello") is True
    assert session.ingest("world") is True
    assert session.line_count == 2
    assert "hello" in session.render_transcript()


def test_render_transcript_uses_session_relative_timestamps() -> None:
    clock = _Clock()
    session = LiveNotesSession("s1", clock=clock)
    session.ingest("first")
    clock.now += 65.0
    session.ingest("second")
    rendered = session.render_transcript()
    assert "[00:00] first" in rendered
    assert "[01:05] second" in rendered


def test_should_refresh_requires_min_chars_and_interval() -> None:
    clock = _Clock()
    session = LiveNotesSession("s1", refresh_seconds=120, min_new_chars=10, clock=clock)
    session.ingest("short")
    assert session.should_refresh() is False
    session.ingest("0123456789")
    assert session.should_refresh() is True


async def test_maybe_refresh_and_snapshot() -> None:
    clock = _Clock()
    session = LiveNotesSession("s1", refresh_seconds=120, min_new_chars=5, clock=clock)
    llm = _FakeLLM()
    session.ingest("line one")
    refreshed = await session.maybe_refresh(llm)
    assert refreshed is not None
    assert refreshed.notes is not None
    assert refreshed.notes.title == "Live Sync"
    assert refreshed.notes.risks == ("Vendor lock-in",)
    assert refreshed.notes.action_items[0].owner == "Alice"
    assert llm.calls == 1

    # Not due again until the interval elapses with new content.
    session.ingest("line two")
    assert await session.maybe_refresh(llm) is None
    assert llm.calls == 1

    clock.now += 200.0
    assert await session.maybe_refresh(llm) is not None
    assert llm.calls == 2


async def test_registry_get_or_create_get_drop() -> None:
    registry = LiveNotesRegistry()
    session = await registry.get_or_create("meeting-1")
    assert session is await registry.get_or_create("meeting-1")
    session.ingest("x")
    assert await registry.get("meeting-1") is session
    await registry.drop("meeting-1")
    assert await registry.get("meeting-1") is None


async def test_concurrent_maybe_refresh_is_single_flight() -> None:
    clock = _Clock()
    session = LiveNotesSession("s1", refresh_seconds=120, min_new_chars=1, clock=clock)
    llm = _FakeLLM()
    session.ingest("line one")
    results = await asyncio.gather(session.maybe_refresh(llm), session.maybe_refresh(llm))
    assert llm.calls == 1
    assert sum(1 for result in results if result is not None) == 1


async def test_registry_evicts_oldest_when_bounded() -> None:
    registry = LiveNotesRegistry(max_sessions=2)
    await registry.get_or_create("a")
    await registry.get_or_create("b")
    await registry.get_or_create("c")
    assert await registry.get("a") is None
    assert await registry.get("b") is not None
    assert await registry.get("c") is not None
