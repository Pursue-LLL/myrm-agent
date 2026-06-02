"""StreamMetrics tests — session tracking, percentiles, alerts."""

from __future__ import annotations

from unittest.mock import patch

from app.channels.routing.stream_metrics import (
    StreamingSession,
    StreamMetrics,
)


class TestStreamingSession:
    def test_defaults(self) -> None:
        s = StreamingSession(session_key="s1")
        assert s.session_key == "s1"
        assert s.edit_count == 0
        assert s.edit_failures == 0
        assert s.chunk_sizes == []
        assert s.api_latencies == []


class TestStreamMetricsStartEnd:
    def test_start_session(self) -> None:
        m = StreamMetrics()
        m.start_session("s1", trace_id="t1")
        assert "s1" in m._sessions

    def test_end_session_removes(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.end_session("s1")
        assert "s1" not in m._sessions

    def test_end_nonexistent_session(self) -> None:
        m = StreamMetrics()
        m.end_session("nonexistent")


class TestRecordEdit:
    def test_record_success(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_edit("s1", text_length=100, success=True, is_first=True)
        s = m._sessions["s1"]
        assert s.edit_count == 1
        assert s.first_edit_at > 0
        assert s.final_text_length == 100

    def test_record_failure(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_edit("s1", text_length=100, success=False)
        s = m._sessions["s1"]
        assert s.edit_failures == 1
        assert s.edit_count == 0

    def test_record_edit_nonexistent_session(self) -> None:
        m = StreamMetrics()
        m.record_edit("nonexistent", text_length=100, success=True)

    def test_chunk_sizes_tracked(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_edit("s1", text_length=50, success=True)
        m.record_edit("s1", text_length=120, success=True)
        s = m._sessions["s1"]
        assert s.chunk_sizes == [50, 70]

    def test_first_edit_only_set_once(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_edit("s1", text_length=50, success=True, is_first=True)
        first = m._sessions["s1"].first_edit_at
        m.record_edit("s1", text_length=100, success=True, is_first=True)
        assert m._sessions["s1"].first_edit_at == first


class TestRecordTransmission:
    def test_accumulates(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_transmission("s1", transmitted_bytes=100, full_text_bytes=200)
        m.record_transmission("s1", transmitted_bytes=50, full_text_bytes=100)
        s = m._sessions["s1"]
        assert s.transmitted_bytes == 150
        assert s.total_bytes == 300

    def test_nonexistent_session(self) -> None:
        m = StreamMetrics()
        m.record_transmission("nonexistent", transmitted_bytes=100, full_text_bytes=200)


class TestRecordApiLatency:
    def test_appends(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_api_latency("s1", 10.5)
        m.record_api_latency("s1", 20.3)
        assert m._sessions["s1"].api_latencies == [10.5, 20.3]

    def test_nonexistent_session(self) -> None:
        m = StreamMetrics()
        m.record_api_latency("nonexistent", 10.0)


class TestRecordDecision:
    def test_appends(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_decision("s1", "first_update")
        m.record_decision("s1", "throttled")
        assert m._sessions["s1"].decision_reasons == ["first_update", "throttled"]

    def test_nonexistent_session(self) -> None:
        m = StreamMetrics()
        m.record_decision("nonexistent", "reason")


class TestSummarizeDecisions:
    def test_empty(self) -> None:
        m = StreamMetrics()
        assert m._summarize_decisions([]) == "none"

    def test_counts(self) -> None:
        m = StreamMetrics()
        result = m._summarize_decisions(["a", "b", "a", "a", "b"])
        assert "a(3)" in result
        assert "b(2)" in result


class TestEndSessionMetrics:
    def test_end_with_edits_and_latencies(self) -> None:
        m = StreamMetrics()
        m.start_session("s1", trace_id="trace-1")
        m.record_edit("s1", text_length=50, success=True, is_first=True)
        m.record_edit("s1", text_length=100, success=True)
        m.record_edit("s1", text_length=100, success=False)
        m.record_api_latency("s1", 10.0)
        m.record_api_latency("s1", 20.0)
        m.record_api_latency("s1", 500.0)
        m.record_transmission("s1", transmitted_bytes=50, full_text_bytes=100)
        m.record_decision("s1", "first_update")

        with patch("app.channels.routing.stream_metrics.logger"):
            m.end_session("s1")

    def test_end_empty_session(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.end_session("s1")

    def test_end_with_no_first_edit(self) -> None:
        m = StreamMetrics()
        m.start_session("s1")
        m.record_edit("s1", text_length=50, success=True, is_first=False)
        m.end_session("s1")


class TestAlerts:
    def test_high_failure_rate_alert(self) -> None:
        alerts: list[str] = []
        m = StreamMetrics(alert_callback=alerts.append, failure_threshold=0.2)
        m.start_session("s1")
        m.record_edit("s1", text_length=50, success=True)
        for _ in range(5):
            m.record_edit("s1", text_length=50, success=False)
        m.end_session("s1")
        assert any("failure rate" in a.lower() for a in alerts)

    def test_high_p95_latency_alert(self) -> None:
        alerts: list[str] = []
        m = StreamMetrics(alert_callback=alerts.append, p95_latency_threshold=100.0)
        m.start_session("s1")
        m.record_edit("s1", text_length=50, success=True)
        for _ in range(20):
            m.record_api_latency("s1", 200.0)
        m.end_session("s1")
        assert any("p95" in a.lower() or "latency" in a.lower() for a in alerts)

    def test_alert_callback_error_silenced(self) -> None:
        def bad_callback(msg: str) -> None:
            raise RuntimeError("callback broken")

        m = StreamMetrics(alert_callback=bad_callback, failure_threshold=0.0)
        m.start_session("s1")
        for _ in range(5):
            m.record_edit("s1", text_length=50, success=False)
        m.end_session("s1")

    def test_no_alert_when_healthy(self) -> None:
        alerts: list[str] = []
        m = StreamMetrics(alert_callback=alerts.append)
        m.start_session("s1")
        m.record_edit("s1", text_length=50, success=True)
        m.record_api_latency("s1", 10.0)
        m.end_session("s1")
        assert len(alerts) == 0
