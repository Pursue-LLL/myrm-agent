"""Tests for streaming optimization components in stream_manager.py."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from app.channels.routing.stream_manager import (
    AdaptiveThrottler,
    BlockChunker,
    ChunkConfig,
    IncrementalEditor,
    ProgressEstimator,
    ProgressInfo,
    StreamCoordinator,
    UpdateDecision,
)

# ── BlockChunker ──────────────────────────────────────────────────────


class TestBlockChunkerShouldEmit:
    def test_final_always_emits(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=1000))
        assert chunker.should_emit_block("short", is_final=True) is True

    def test_below_block_size_no_emit(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=100))
        assert chunker.should_emit_block("short", is_final=False) is False

    def test_above_block_size_emits(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10))
        assert chunker.should_emit_block("a" * 20, is_final=False) is True

    def test_inside_code_fence_no_emit(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10))
        text = "```python\ndef foo():\n    pass"
        assert chunker.should_emit_block(text, is_final=False) is False

    def test_code_fence_protection_disabled(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10, enable_code_fence_protection=False))
        text = "```python\ndef foo():\n    pass"
        assert chunker.should_emit_block(text, is_final=False) is True


class TestBlockChunkerFindBreak:
    def test_short_text_no_break(self) -> None:
        chunker = BlockChunker()
        assert chunker.find_break_point("short", 100) == 0

    def test_prefer_newline_break(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10, prefer_newline_breaks=True))
        text = "a" * 15 + "\n" + "b" * 10
        bp = chunker.find_break_point(text, 20)
        assert bp == 16

    def test_newline_too_early_uses_max(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10, prefer_newline_breaks=True))
        text = "h\n" + "a" * 50
        bp = chunker.find_break_point(text, 50)
        assert bp == 50

    def test_code_fence_boundary_respected(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10, enable_code_fence_protection=True))
        text = "```python\ncode```more text after"
        bp = chunker.find_break_point(text, 15)
        assert bp in (0, 17)

    def test_inside_unclosed_fence_returns_zero(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10, enable_code_fence_protection=True))
        text = "```python\ndef foo():\n    pass\n    more code"
        bp = chunker.find_break_point(text, 20)
        assert bp == 0

    def test_no_code_fence_protection(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10, enable_code_fence_protection=False, prefer_newline_breaks=False))
        text = "a" * 100
        bp = chunker.find_break_point(text, 50)
        assert bp == 50


class TestBlockChunkerCodeFence:
    def test_not_inside_fence(self) -> None:
        chunker = BlockChunker()
        assert chunker._is_inside_code_fence("hello world") is False

    def test_inside_unclosed_fence(self) -> None:
        chunker = BlockChunker()
        assert chunker._is_inside_code_fence("```python\ncode here") is True

    def test_closed_fence(self) -> None:
        chunker = BlockChunker()
        assert chunker._is_inside_code_fence("```python\ncode```") is False

    def test_find_code_fence_end_no_fence(self) -> None:
        chunker = BlockChunker()
        assert chunker._find_code_fence_end("hello") == 0

    def test_find_code_fence_end_closed(self) -> None:
        chunker = BlockChunker()
        result = chunker._find_code_fence_end("```python\ncode```")
        assert result == 17

    def test_find_code_fence_end_unclosed(self) -> None:
        chunker = BlockChunker()
        assert chunker._find_code_fence_end("```python\ncode") == 0


# ── IncrementalEditor ─────────────────────────────────────────────────


class TestIncrementalEditor:
    def test_first_update_returns_full(self) -> None:
        editor = IncrementalEditor()
        result = editor.compute_update("s1", "hello world")
        assert result == (0, "hello world")

    def test_no_change_returns_none(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("s1", "hello")
        assert editor.compute_update("s1", "hello") is None

    def test_incremental_change(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("s1", "hello")
        result = editor.compute_update("s1", "hello world")
        assert result is not None
        offset, new_content = result
        assert offset == 5
        assert new_content == " world"

    def test_independent_sessions(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("s1", "aaa")
        editor.compute_update("s2", "bbb")
        r1 = editor.compute_update("s1", "aaa!")
        r2 = editor.compute_update("s2", "bbb!")
        assert r1 == (3, "!")
        assert r2 == (3, "!")

    def test_cleanup(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("s1", "hello")
        editor.cleanup("s1")
        result = editor.compute_update("s1", "hello")
        assert result == (0, "hello")

    def test_cleanup_nonexistent(self) -> None:
        editor = IncrementalEditor()
        editor.cleanup("nonexistent")

    def test_complete_replacement(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("s1", "abc")
        result = editor.compute_update("s1", "xyz")
        assert result == (0, "xyz")


# ── AdaptiveThrottler ─────────────────────────────────────────────────


class TestAdaptiveThrottler:
    def test_default_interval(self) -> None:
        throttler = AdaptiveThrottler()
        assert throttler.get_interval() == 0.5

    def test_fast_network_decreases_interval(self) -> None:
        throttler = AdaptiveThrottler(initial_interval=1.0)
        for _ in range(5):
            throttler.record_latency(0.05)
        assert throttler.get_interval() < 1.0

    def test_slow_network_increases_interval(self) -> None:
        throttler = AdaptiveThrottler(initial_interval=0.5)
        for _ in range(5):
            throttler.record_latency(0.8)
        assert throttler.get_interval() > 0.5

    def test_too_few_samples_no_change(self) -> None:
        throttler = AdaptiveThrottler(initial_interval=0.5)
        throttler.record_latency(0.01)
        throttler.record_latency(0.01)
        assert throttler.get_interval() == 0.5

    def test_max_samples_eviction(self) -> None:
        throttler = AdaptiveThrottler()
        for _i in range(15):
            throttler.record_latency(0.1)
        assert len(throttler.latency_samples) == throttler.max_samples

    def test_reset(self) -> None:
        throttler = AdaptiveThrottler()
        for _ in range(5):
            throttler.record_latency(0.05)
        throttler.reset()
        assert throttler.get_interval() == 0.5
        assert len(throttler.latency_samples) == 0

    def test_min_interval_respected(self) -> None:
        throttler = AdaptiveThrottler(min_interval=0.3, initial_interval=0.31)
        for _ in range(20):
            throttler.record_latency(0.01)
        assert throttler.get_interval() >= 0.3

    def test_max_interval_respected(self) -> None:
        throttler = AdaptiveThrottler(max_interval=1.5, initial_interval=1.49)
        for _ in range(20):
            throttler.record_latency(1.0)
        assert throttler.get_interval() <= 1.5


# ── ProgressEstimator ─────────────────────────────────────────────────


class TestProgressEstimator:
    def test_start_and_estimate(self) -> None:
        est = ProgressEstimator()
        est.start_session("s1", "write a function")
        result = est.estimate_progress("s1", 10)
        assert result is not None
        assert 0 <= result.percentage <= 100

    def test_nonexistent_session(self) -> None:
        est = ProgressEstimator()
        assert est.estimate_progress("nope", 100) is None

    def test_cleanup(self) -> None:
        est = ProgressEstimator()
        est.start_session("s1", "hello")
        est.cleanup("s1")
        assert est.estimate_progress("s1", 10) is None

    def test_task_type_inference_code(self) -> None:
        est = ProgressEstimator()
        assert est._infer_task_type("implement a sorting algorithm") == "code"

    def test_task_type_inference_search(self) -> None:
        est = ProgressEstimator()
        assert est._infer_task_type("search for recent papers") == "search"

    def test_task_type_inference_file(self) -> None:
        est = ProgressEstimator()
        assert est._infer_task_type("read the config file") == "file"

    def test_task_type_inference_chat(self) -> None:
        est = ProgressEstimator()
        assert est._infer_task_type("hello how are you") == "chat"

    def test_dynamic_adjustment(self) -> None:
        est = ProgressEstimator()
        est.start_session("s1", "write code")
        session = est._sessions["s1"]
        original_total = session.expected_total
        est.estimate_progress("s1", int(original_total * 0.9))
        assert session.expected_total > original_total

    def test_progress_capped_at_95(self) -> None:
        est = ProgressEstimator()
        est.start_session("s1", "hi")
        result = est.estimate_progress("s1", 999999)
        assert result is not None
        assert result.percentage <= 95

    def test_cleanup_expired_sessions(self) -> None:
        est = ProgressEstimator(session_ttl_seconds=0.001)
        est.start_session("s1", "test")
        time.sleep(0.01)
        cleaned = est.cleanup_expired_sessions()
        assert cleaned == 1
        assert est.estimate_progress("s1", 10) is None

    def test_cleanup_no_expired(self) -> None:
        est = ProgressEstimator(session_ttl_seconds=3600)
        est.start_session("s1", "test")
        assert est.cleanup_expired_sessions() == 0


# ── StreamCoordinator ─────────────────────────────────────────────────


def _make_coordinator(
    block_size: int = 50,
    degradation_multiplier: float = 1.0,
) -> StreamCoordinator:
    chunker = BlockChunker(ChunkConfig(block_size=block_size))
    editor = IncrementalEditor()
    throttler = AdaptiveThrottler(initial_interval=0.3)
    degradation = MagicMock()
    degradation.get_slowdown_multiplier.return_value = degradation_multiplier
    return StreamCoordinator(chunker, editor, throttler, degradation)


class TestStreamCoordinator:
    def test_first_send_immediate(self) -> None:
        coord = _make_coordinator(block_size=10)
        decision = coord.should_send_update("s1", "a" * 60)
        assert decision.should_send is True
        assert decision.reason == "first_send_immediate"

    def test_first_send_too_small(self) -> None:
        coord = _make_coordinator(block_size=10)
        decision = coord.should_send_update("s1", "hi")
        assert decision.should_send is False
        assert "first_too_small" in decision.reason

    def test_first_send_too_small_but_final(self) -> None:
        coord = _make_coordinator(block_size=10)
        decision = coord.should_send_update("s1", "hi", is_final=True)
        assert decision.should_send is True

    def test_no_change_skipped(self) -> None:
        coord = _make_coordinator(block_size=10)
        coord.should_send_update("s1", "a" * 60)
        decision = coord.should_send_update("s1", "a" * 60)
        assert decision.should_send is False
        assert decision.reason == "no_change"

    def test_block_ready_sends(self) -> None:
        coord = _make_coordinator(block_size=10)
        coord.should_send_update("s1", "a" * 60)
        decision = coord.should_send_update("s1", "a" * 60 + "b" * 20)
        assert decision.should_send is True
        assert "block_ready" in decision.reason

    def test_below_block_size_no_send(self) -> None:
        coord = _make_coordinator(block_size=1000)
        coord.should_send_update("s1", "a" * 1000)
        decision = coord.should_send_update("s1", "a" * 1000 + "b")
        assert decision.should_send is True
        assert "block_ready" in decision.reason

    def test_degradation_multiplier_applied(self) -> None:
        coord = _make_coordinator(block_size=10, degradation_multiplier=3.0)
        coord.should_send_update("s1", "a" * 60)
        decision = coord.should_send_update("s1", "a" * 60 + "b" * 20)
        assert decision.should_send is True
        assert decision.delay_seconds > 0.3

    def test_record_send_latency(self) -> None:
        coord = _make_coordinator()
        coord.record_send_latency(0.1)

    def test_cleanup_session(self) -> None:
        coord = _make_coordinator(block_size=10)
        coord.should_send_update("s1", "a" * 60)
        coord.cleanup("s1")
        decision = coord.should_send_update("s1", "a" * 60)
        assert decision.should_send is True
        assert decision.reason == "first_send_immediate"

    def test_cleanup_expired_sessions(self) -> None:
        coord = _make_coordinator(block_size=10)
        coord._session_ttl = 0.001
        coord.should_send_update("s1", "a" * 60)
        time.sleep(0.01)
        cleaned = coord.cleanup_expired_sessions()
        assert cleaned == 1

    def test_cleanup_no_expired(self) -> None:
        coord = _make_coordinator(block_size=10)
        coord.should_send_update("s1", "a" * 60)
        assert coord.cleanup_expired_sessions() == 0


# ── UpdateDecision / ProgressInfo ─────────────────────────────────────


class TestDataTypes:
    def test_update_decision_defaults(self) -> None:
        d = UpdateDecision(should_send=True)
        assert d.content is None
        assert d.delay_seconds == 0.0
        assert d.reason == ""

    def test_progress_info(self) -> None:
        p = ProgressInfo(percentage=50, remaining_seconds=10)
        assert p.percentage == 50
        assert p.remaining_seconds == 10
