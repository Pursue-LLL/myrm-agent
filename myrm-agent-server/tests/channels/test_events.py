"""Tests for core/events.py — EventEmitter."""

from __future__ import annotations

from typing import Any

from app.channels.core.events import EventEmitter


class TestEventEmitter:
    def test_emit_calls_listener(self) -> None:
        emitter = EventEmitter("test")
        received: list[tuple[str, Any]] = []
        emitter.on("evt", lambda name, data: received.append((name, data)))
        emitter.emit("evt", {"key": "val"})
        assert received == [("test", {"key": "val"})]

    def test_multiple_listeners(self) -> None:
        emitter = EventEmitter("test")
        calls: list[int] = []
        emitter.on("evt", lambda n, d: calls.append(1))
        emitter.on("evt", lambda n, d: calls.append(2))
        emitter.emit("evt")
        assert calls == [1, 2]

    def test_emit_no_listeners(self) -> None:
        emitter = EventEmitter("test")
        emitter.emit("no_listeners")

    def test_off_removes_listener(self) -> None:
        emitter = EventEmitter("test")
        calls: list[int] = []

        def listener(_n: str, _d: object) -> None:
            calls.append(1)

        emitter.on("evt", listener)
        emitter.off("evt", listener)
        emitter.emit("evt")
        assert calls == []

    def test_off_nonexistent_listener(self) -> None:
        emitter = EventEmitter("test")
        emitter.off("evt", lambda n, d: None)

    def test_off_nonexistent_event(self) -> None:
        emitter = EventEmitter("test")
        emitter.off("missing", lambda n, d: None)

    def test_listener_error_does_not_stop_others(self) -> None:
        emitter = EventEmitter("test")
        calls: list[int] = []

        def bad_listener(name: str, data: Any) -> None:
            raise ValueError("boom")

        emitter.on("evt", bad_listener)
        emitter.on("evt", lambda n, d: calls.append(1))
        emitter.emit("evt")
        assert calls == [1]

    def test_clear_specific_event(self) -> None:
        emitter = EventEmitter("test")
        calls: list[str] = []
        emitter.on("a", lambda n, d: calls.append("a"))
        emitter.on("b", lambda n, d: calls.append("b"))
        emitter.clear_listeners("a")
        emitter.emit("a")
        emitter.emit("b")
        assert calls == ["b"]

    def test_clear_all_events(self) -> None:
        emitter = EventEmitter("test")
        calls: list[str] = []
        emitter.on("a", lambda n, d: calls.append("a"))
        emitter.on("b", lambda n, d: calls.append("b"))
        emitter.clear_listeners()
        emitter.emit("a")
        emitter.emit("b")
        assert calls == []

    def test_emit_with_none_data(self) -> None:
        emitter = EventEmitter("test")
        received: list[Any] = []
        emitter.on("evt", lambda n, d: received.append(d))
        emitter.emit("evt")
        assert received == [None]
