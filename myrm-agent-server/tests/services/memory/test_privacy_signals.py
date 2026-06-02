"""Tests for build_privacy_signals() in MemoryCommandCenterInsights.

Validates three-state logic for secret_redaction signal:
- missing: zero scans recorded
- ready: scans recorded, no blocked/redacted events
- warning: scans recorded, with blocked/redacted events
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory._internal.memory_scanner import ScanVerdict, get_scan_metrics

from app.schemas.memory.command_center import MemoryCommandTimelineEvent
from app.services.memory.command_center_insights import MemoryCommandCenterInsights


def _make_event(*, status: str = "ok", kind: str = "store") -> MemoryCommandTimelineEvent:
    return MemoryCommandTimelineEvent(
        id="e1",
        kind=kind,
        status=status,
        occurred_at=datetime.now(UTC),
        title="test",
        description="test event",
        source="test",
    )


class TestBuildPrivacySignals:
    """build_privacy_signals() — secret_redaction three-state logic."""

    def setup_method(self) -> None:
        get_scan_metrics().reset()

    def _find_redaction_signal(
        self, signals: list[object],
    ) -> object:
        for s in signals:
            if getattr(s, "id", None) == "secret_redaction":
                return s
        raise AssertionError("secret_redaction signal not found")

    def test_no_scans_returns_missing(self) -> None:
        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.status == "missing"
        assert sig.event_count == 0
        assert "0 scans" in sig.evidence

    def test_clean_scans_returns_ready(self) -> None:
        metrics = get_scan_metrics()
        metrics.record(ScanVerdict.CLEAN)
        metrics.record(ScanVerdict.CLEAN)
        metrics.record(ScanVerdict.WARN)

        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.status == "ready"
        assert sig.event_count == 0

    def test_blocked_scans_returns_warning(self) -> None:
        metrics = get_scan_metrics()
        metrics.record(ScanVerdict.CLEAN)
        metrics.record(ScanVerdict.BLOCKED)
        metrics.record(ScanVerdict.REDACTED)

        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.status == "warning"
        assert sig.event_count == 2
        assert "2 blocked or redacted" in sig.evidence

    def test_only_redacted_returns_warning(self) -> None:
        metrics = get_scan_metrics()
        metrics.record(ScanVerdict.REDACTED)

        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.status == "warning"
        assert sig.event_count == 1

    def test_approval_gate_always_present(self) -> None:
        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        ids = [s.id for s in signals]
        assert "approval_gate" in ids
        assert "sensitive_event_visibility" in ids
        assert "secret_redaction" in ids

    def test_sensitive_event_visibility_with_warnings(self) -> None:
        timeline = [_make_event(status="warning"), _make_event(status="ok")]
        signals = MemoryCommandCenterInsights.build_privacy_signals(timeline)
        vis_signal = next(s for s in signals if s.id == "sensitive_event_visibility")
        assert vis_signal.status == "warning"
        assert vis_signal.event_count == 1

    def test_approval_gate_counts_approve_reject(self) -> None:
        timeline = [
            _make_event(kind="approve"),
            _make_event(kind="reject"),
            _make_event(kind="store"),
        ]
        signals = MemoryCommandCenterInsights.build_privacy_signals(timeline)
        gate_signal = next(s for s in signals if s.id == "approval_gate")
        assert gate_signal.event_count == 2

    def test_only_blocked_no_redacted_returns_warning(self) -> None:
        metrics = get_scan_metrics()
        metrics.record(ScanVerdict.CLEAN)
        metrics.record(ScanVerdict.BLOCKED)

        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.status == "warning"
        assert sig.event_count == 1

    def test_warn_only_does_not_trigger_warning_status(self) -> None:
        """WARN verdicts are not security events — status should be 'ready'."""
        metrics = get_scan_metrics()
        metrics.record(ScanVerdict.WARN)
        metrics.record(ScanVerdict.WARN)
        metrics.record(ScanVerdict.WARN)

        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.status == "ready"
        assert sig.event_count == 0

    def test_high_volume_scans_accuracy(self) -> None:
        metrics = get_scan_metrics()
        for _ in range(1000):
            metrics.record(ScanVerdict.CLEAN)
        metrics.record(ScanVerdict.BLOCKED)
        metrics.record(ScanVerdict.REDACTED)

        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.status == "warning"
        assert sig.event_count == 2
        assert "1002 scans" in sig.evidence

    def test_sensitive_event_visibility_with_errors(self) -> None:
        timeline = [_make_event(status="error"), _make_event(status="warning")]
        signals = MemoryCommandCenterInsights.build_privacy_signals(timeline)
        vis_signal = next(s for s in signals if s.id == "sensitive_event_visibility")
        assert vis_signal.status == "warning"
        assert vis_signal.event_count == 2

    def test_sensitive_event_visibility_all_ok_is_ready(self) -> None:
        timeline = [_make_event(status="ok"), _make_event(status="ok")]
        signals = MemoryCommandCenterInsights.build_privacy_signals(timeline)
        vis_signal = next(s for s in signals if s.id == "sensitive_event_visibility")
        assert vis_signal.status == "ready"
        assert vis_signal.event_count == 0

    def test_evidence_text_format(self) -> None:
        metrics = get_scan_metrics()
        metrics.record(ScanVerdict.BLOCKED)
        metrics.record(ScanVerdict.BLOCKED)
        metrics.record(ScanVerdict.CLEAN)

        signals = MemoryCommandCenterInsights.build_privacy_signals([])
        sig = self._find_redaction_signal(signals)
        assert sig.evidence == "2 blocked or redacted events out of 3 scans."

    def test_signal_count_always_three(self) -> None:
        """build_privacy_signals always returns exactly 3 signals."""
        for timeline in [[], [_make_event()], [_make_event(status="error")]]:
            signals = MemoryCommandCenterInsights.build_privacy_signals(timeline)
            assert len(signals) == 3
