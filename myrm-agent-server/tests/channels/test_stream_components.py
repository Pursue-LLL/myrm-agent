"""Unit tests for streaming components: BlockChunker, IncrementalEditor, AdaptiveThrottler, etc."""

from app.channels.routing.stream_manager import (
    AdaptiveThrottler,
    BlockChunker,
    ChunkConfig,
    IncrementalEditor,
    ProgressEstimator,
    StreamCoordinator,
)
from app.channels.routing.stream_metrics import StreamMetrics


class TestBlockChunker:
    """Test intelligent block chunking with code fence protection."""

    def test_code_fence_detection_single_fence(self) -> None:
        chunker = BlockChunker()
        text = "Here is code:\n```python\ndef foo():\n    pass"
        assert chunker._is_inside_code_fence(text) is True

    def test_code_fence_detection_closed(self) -> None:
        chunker = BlockChunker()
        text = "Here is code:\n```python\ndef foo():\n    pass\n```\nDone"
        assert chunker._is_inside_code_fence(text) is False

    def test_code_fence_detection_multiple(self) -> None:
        chunker = BlockChunker()
        text = "First:\n```js\ncode\n```\nSecond:\n```py\nmore"
        assert chunker._is_inside_code_fence(text) is True

    def test_find_code_fence_end_unclosed(self) -> None:
        chunker = BlockChunker()
        text = "Start\n```python\ndef foo():\n    pass"
        end_pos = chunker._find_code_fence_end(text)
        assert end_pos == 0

    def test_find_code_fence_end_closed(self) -> None:
        chunker = BlockChunker()
        text = "Start\n```python\ndef foo():\n    pass\n```"
        end_pos = chunker._find_code_fence_end(text)
        assert end_pos == len(text)

    def test_should_emit_below_threshold(self) -> None:
        config = ChunkConfig(block_size=500)
        chunker = BlockChunker(config)
        assert chunker.should_emit_block("short text", is_final=False) is False

    def test_should_emit_above_threshold_no_fence(self) -> None:
        config = ChunkConfig(block_size=10)
        chunker = BlockChunker(config)
        text = "a" * 100
        assert chunker.should_emit_block(text, is_final=False) is True

    def test_should_emit_above_threshold_inside_fence(self) -> None:
        config = ChunkConfig(block_size=10, enable_code_fence_protection=True)
        chunker = BlockChunker(config)
        text = "```python\n" + "a" * 100
        assert chunker.should_emit_block(text, is_final=False) is False

    def test_should_emit_final_always_true(self) -> None:
        chunker = BlockChunker()
        assert chunker.should_emit_block("any", is_final=True) is True

    def test_find_break_point_prefer_newline(self) -> None:
        config = ChunkConfig(block_size=100, prefer_newline_breaks=True)
        chunker = BlockChunker(config)
        text = "a" * 80 + "\n" + "b" * 50
        break_point = chunker.find_break_point(text, 100)
        assert break_point == 81

    def test_find_break_point_no_newline(self) -> None:
        config = ChunkConfig(block_size=100, prefer_newline_breaks=False)
        chunker = BlockChunker(config)
        text = "a" * 150
        break_point = chunker.find_break_point(text, 100)
        assert break_point == 100

    def test_find_break_point_code_fence_protection_unclosed(self) -> None:
        config = ChunkConfig(block_size=20, enable_code_fence_protection=True)
        chunker = BlockChunker(config)
        text = "Start\n```python\ndef foo():\n    pass"
        break_point = chunker.find_break_point(text, 20)
        assert break_point == 0

    def test_find_break_point_code_fence_protection_closed(self) -> None:
        config = ChunkConfig(block_size=20, enable_code_fence_protection=True)
        chunker = BlockChunker(config)
        text = "Start\n```python\ndef foo():\n    pass\n```\nMore text here"
        break_point = chunker.find_break_point(text, 40)
        fence_end = text.index("```\nMore") + 3
        assert break_point == fence_end


class TestIncrementalEditor:
    """Test incremental text editing for change tracking."""

    def test_first_update_returns_full_text(self) -> None:
        editor = IncrementalEditor()
        result = editor.compute_update("session1", "Hello World")
        assert result == (0, "Hello World")

    def test_no_change_returns_none(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("session1", "Hello World")
        result = editor.compute_update("session1", "Hello World")
        assert result is None

    def test_incremental_update(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("session1", "Hello")
        result = editor.compute_update("session1", "Hello World")
        assert result == (5, " World")

    def test_incremental_update_large_text(self) -> None:
        editor = IncrementalEditor()
        text1 = "A" * 3000
        text2 = text1 + "B" * 100
        editor.compute_update("session1", text1)
        result = editor.compute_update("session1", text2)
        assert result == (3000, "B" * 100)

    def test_cleanup_removes_session(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("session1", "Hello")
        editor.cleanup("session1")
        result = editor.compute_update("session1", "Hello")
        assert result == (0, "Hello")

    def test_multiple_sessions(self) -> None:
        editor = IncrementalEditor()
        result1 = editor.compute_update("session1", "Hello")
        result2 = editor.compute_update("session2", "World")
        assert result1 == (0, "Hello")
        assert result2 == (0, "World")

    def test_text_replacement(self) -> None:
        editor = IncrementalEditor()
        editor.compute_update("session1", "Hello World")
        result = editor.compute_update("session1", "Hello Universe")
        assert result == (6, "Universe")


class TestAdaptiveThrottler:
    """Test adaptive throttling based on network latency."""

    def test_initial_interval(self) -> None:
        throttler = AdaptiveThrottler()
        assert throttler.get_interval() == 0.5

    def test_fast_network_reduces_interval(self) -> None:
        throttler = AdaptiveThrottler()
        for _ in range(5):
            throttler.record_latency(0.05)
        assert throttler.get_interval() < 0.5

    def test_slow_network_increases_interval(self) -> None:
        throttler = AdaptiveThrottler()
        for _ in range(5):
            throttler.record_latency(0.8)
        assert throttler.get_interval() > 0.5

    def test_interval_respects_min_bound(self) -> None:
        throttler = AdaptiveThrottler(min_interval=0.2)
        for _ in range(20):
            throttler.record_latency(0.01)
        assert throttler.get_interval() >= 0.2

    def test_interval_respects_max_bound(self) -> None:
        throttler = AdaptiveThrottler(max_interval=2.0)
        for _ in range(20):
            throttler.record_latency(1.5)
        assert throttler.get_interval() <= 2.0

    def test_samples_window_limit(self) -> None:
        throttler = AdaptiveThrottler()
        for i in range(15):
            throttler.record_latency(0.1 * i)
        assert len(throttler.latency_samples) == 10

    def test_reset_clears_state(self) -> None:
        throttler = AdaptiveThrottler()
        for _ in range(5):
            throttler.record_latency(0.8)
        throttler.reset()
        assert throttler.get_interval() == 0.5
        assert len(throttler.latency_samples) == 0

    def test_insufficient_samples_no_adjustment(self) -> None:
        throttler = AdaptiveThrottler()
        initial = throttler.get_interval()
        throttler.record_latency(0.01)
        assert throttler.get_interval() == initial

    def test_mixed_latency_converges(self) -> None:
        throttler = AdaptiveThrottler()
        for _ in range(3):
            throttler.record_latency(0.05)
            throttler.record_latency(0.6)
        interval = throttler.get_interval()
        assert 0.4 < interval < 0.7


class TestProgressEstimator:
    """Test progress estimation and remaining time prediction."""

    def test_initial_progress_low(self) -> None:
        estimator = ProgressEstimator()
        estimator.start_session("session1", prompt="A" * 100)
        progress = estimator.estimate_progress("session1", current_output_length=10)

        assert progress is not None
        assert progress.percentage < 20

    def test_progress_increases(self) -> None:
        estimator = ProgressEstimator()
        estimator.start_session("session1", prompt="A" * 100)
        progress1 = estimator.estimate_progress("session1", current_output_length=50)
        progress2 = estimator.estimate_progress("session1", current_output_length=100)

        assert progress1 is not None
        assert progress2 is not None
        assert progress2.percentage > progress1.percentage

    def test_progress_never_reaches_100(self) -> None:
        estimator = ProgressEstimator()
        estimator.start_session("session1", prompt="A" * 100)
        progress = estimator.estimate_progress("session1", current_output_length=10000)

        assert progress is not None
        assert progress.percentage <= 95

    def test_cleanup_removes_session(self) -> None:
        estimator = ProgressEstimator()
        estimator.start_session("session1", prompt="A" * 100)
        estimator.cleanup("session1")
        progress = estimator.estimate_progress("session1", current_output_length=50)

        assert progress is None

    def test_multiple_sessions(self) -> None:
        estimator = ProgressEstimator()
        estimator.start_session("session1", prompt="A" * 100)
        estimator.start_session("session2", prompt="A" * 200)

        progress1 = estimator.estimate_progress("session1", current_output_length=50)
        progress2 = estimator.estimate_progress("session2", current_output_length=100)

        assert progress1 is not None
        assert progress2 is not None


class TestStreamCoordinator:
    """Test unified streaming coordinator."""

    @staticmethod
    def _create_coordinator(**kwargs) -> StreamCoordinator:
        """Helper to create coordinator with default degradation controller."""
        from app.channels.routing.graceful_degradation import (
            GracefulDegradationController,
        )

        chunker = kwargs.get("chunker", BlockChunker())
        editor = kwargs.get("editor", IncrementalEditor())
        throttler = kwargs.get("throttler", AdaptiveThrottler())
        degradation = kwargs.get("degradation", GracefulDegradationController())
        return StreamCoordinator(chunker, editor, throttler, degradation)

    def test_first_send_decision(self) -> None:
        coordinator = self._create_coordinator()

        text = "A" * 100
        decision = coordinator.should_send_update("session1", text, is_final=False)

        assert decision.should_send is True
        assert decision.delay_seconds == 0.0

    def test_subsequent_send_requires_block_size(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=500))
        coordinator = self._create_coordinator(chunker=chunker)

        coordinator.should_send_update("session1", "Hello", is_final=False)
        decision = coordinator.should_send_update("session1", "Hello World", is_final=False)

        assert decision.should_send is False

    def test_final_update_always_sent(self) -> None:
        coordinator = self._create_coordinator()

        coordinator.should_send_update("session1", "Hello", is_final=False)
        decision = coordinator.should_send_update("session1", "Hello!", is_final=True)

        assert decision.should_send is True

    def test_adaptive_interval_applied(self) -> None:
        chunker = BlockChunker(ChunkConfig(block_size=10))
        throttler = AdaptiveThrottler()
        coordinator = self._create_coordinator(chunker=chunker, throttler=throttler)

        for _ in range(5):
            throttler.record_latency(0.05)

        coordinator.should_send_update("session1", "A" * 100, is_final=False)
        decision = coordinator.should_send_update("session1", "A" * 200, is_final=False)

        assert decision.should_send is True
        assert decision.delay_seconds < 0.5

    def test_cleanup_removes_session(self) -> None:
        coordinator = self._create_coordinator()

        text = "A" * 100
        coordinator.should_send_update("session1", text, is_final=False)
        coordinator.cleanup("session1")
        decision = coordinator.should_send_update("session1", text, is_final=False)

        assert decision.should_send is True


class TestStreamMetrics:
    """Test streaming quality metrics with enhanced features."""

    def test_basic_session_tracking(self) -> None:
        metrics = StreamMetrics()
        metrics.start_session("session1")
        metrics.record_edit("session1", text_length=100, success=True, is_first=True)
        metrics.end_session("session1")

    def test_transmission_efficiency_tracking(self) -> None:
        metrics = StreamMetrics()
        metrics.start_session("session1")
        metrics.record_transmission("session1", transmitted_bytes=100, full_text_bytes=1000)
        metrics.record_transmission("session1", transmitted_bytes=50, full_text_bytes=1000)
        metrics.end_session("session1")

    def test_api_latency_tracking(self) -> None:
        metrics = StreamMetrics()
        metrics.start_session("session1")
        for latency in [100.0, 150.0, 200.0, 120.0, 180.0]:
            metrics.record_api_latency("session1", latency)
        metrics.end_session("session1")

    def test_alert_on_high_failure_rate(self) -> None:
        alert_msg = None

        def alert_callback(msg: str) -> None:
            nonlocal alert_msg
            alert_msg = msg

        metrics = StreamMetrics(alert_callback=alert_callback, failure_threshold=0.3)
        metrics.start_session("session1")
        metrics.record_edit("session1", 100, success=True, is_first=True)
        metrics.record_edit("session1", 200, success=False)
        metrics.record_edit("session1", 300, success=False)
        metrics.record_edit("session1", 400, success=False)
        metrics.end_session("session1")

        assert alert_msg is not None
        assert "failure" in alert_msg.lower() or "rate" in alert_msg.lower()

    def test_alert_on_high_p95_latency(self) -> None:
        alert_msg = None

        def alert_callback(msg: str) -> None:
            nonlocal alert_msg
            alert_msg = msg

        metrics = StreamMetrics(alert_callback=alert_callback, p95_latency_threshold=500.0)
        metrics.start_session("session1")
        metrics.record_edit("session1", 100, success=True, is_first=True)
        for _ in range(100):
            metrics.record_api_latency("session1", 600.0)
        metrics.end_session("session1")

        assert alert_msg is not None
        assert "latency" in alert_msg.lower()
