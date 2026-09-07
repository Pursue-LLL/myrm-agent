"""Unit tests for BurnRateSmokeAlarmDetector."""

import time
import pytest

from app.services.observability.burn_rate_smoke_alarm import (
    BurnRateSmokeAlarmDetector,
    SmokeAlarmVerdict,
)


def test_smoke_alarm_normal_usage() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=60.0, threshold_tpm=100_000.0)
    now = time.monotonic()

    # Small usage: 2000 tokens in 10 seconds -> ~12k TPM (below 100k)
    v1 = detector.record_usage("session-1", 1000, timestamp=now)
    v2 = detector.record_usage("session-1", 1000, timestamp=now + 10.0)

    assert not v2.is_alert
    assert v2.total_tokens_in_window == 2000
    assert v2.tokens_per_minute < 100_000.0


def test_smoke_alarm_rapid_spike() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=60.0, threshold_tpm=100_000.0)
    now = time.monotonic()

    # Rapid spike: 30,000 tokens in 5 seconds -> (30,000 / 5) * 60 = 360,000 TPM
    detector.record_usage("session-runaway", 10_000, timestamp=now)
    v2 = detector.record_usage("session-runaway", 20_000, timestamp=now + 5.0)

    assert v2.is_alert
    assert v2.total_tokens_in_window == 30_000
    assert v2.tokens_per_minute >= 100_000.0
    assert "exceeded threshold" in v2.reason

    active_alerts = detector.get_active_alerts()
    assert len(active_alerts) == 1
    assert active_alerts[0]["session_id"] == "session-runaway"


def test_smoke_alarm_stale_eviction() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=10.0, threshold_tpm=50_000.0)
    now = time.monotonic()

    # Old spike 20 seconds ago
    detector.record_usage("session-stale", 25_000, timestamp=now - 20.0)

    # Check now: old usage should be evicted
    verdict = detector.check_verdict("session-stale")
    assert not verdict.is_alert
    assert verdict.total_tokens_in_window == 0


def test_smoke_alarm_reset() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=60.0, threshold_tpm=50_000.0)
    now = time.monotonic()

    detector.record_usage("session-a", 30_000, timestamp=now)
    detector.record_usage("session-b", 30_000, timestamp=now)

    detector.reset("session-a")
    assert detector.check_verdict("session-a").total_tokens_in_window == 0
    assert detector.check_verdict("session-b").total_tokens_in_window == 30_000

    detector.reset()
    assert detector.check_verdict("session-b").total_tokens_in_window == 0
