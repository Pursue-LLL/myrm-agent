"""Unit tests for BurnRateSmokeAlarmDetector."""

import time

from app.services.observability.burn_rate_smoke_alarm import (
    BurnRateSmokeAlarmDetector,
)


def test_smoke_alarm_normal_usage() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=60.0, threshold_tpm=100_000.0)
    now = time.monotonic()

    # Small usage: 2000 tokens in 10 seconds -> ~12k TPM (below 100k)
    detector.record_usage("session-1", 1000, timestamp=now)
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


def test_smoke_alarm_zero_or_negative_tokens() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=60.0, threshold_tpm=50_000.0)
    v1 = detector.record_usage("session-zero", 0)
    assert not v1.is_alert
    assert v1.total_tokens_in_window == 0

    v2 = detector.record_usage("session-zero", -10)
    assert not v2.is_alert
    assert v2.total_tokens_in_window == 0


def test_smoke_alarm_global_aggregate_and_single_point() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=60.0, threshold_tpm=50_000.0)
    now = time.monotonic()

    # Record 1000 tokens for session-1 (single point span defaults to 1.0s -> 60,000 TPM, but total_tokens < 20,000 so not alert)
    v1 = detector.record_usage("session-1", 1000, timestamp=now)
    assert not v1.is_alert
    assert v1.tokens_per_minute == 60_000.0
    assert v1.total_tokens_in_window == 1000

    # Record for session-2
    detector.record_usage("session-2", 2000, timestamp=now + 1.0)

    # Check global aggregate (session_id=None)
    global_v = detector.check_verdict()
    assert global_v.total_tokens_in_window == 3000
    assert not global_v.is_alert

    # Check empty check_verdict for unknown session
    unknown_v = detector.check_verdict("unknown-session")
    assert not unknown_v.is_alert
    assert unknown_v.total_tokens_in_window == 0


def test_smoke_alarm_stale_record_pruned_on_query() -> None:
    detector = BurnRateSmokeAlarmDetector(window_seconds=10.0, threshold_tpm=50_000.0)
    now = time.monotonic()
    # Record usage that occurred 20 seconds ago
    detector.record_usage("session-expired", 500, timestamp=now - 20.0)
    assert "session-expired" in detector._sessions

    # check_verdict will prune the queue, pop the session, and return empty verdict
    v = detector.check_verdict("session-expired")
    assert not v.is_alert
    assert v.total_tokens_in_window == 0
    assert "session-expired" not in detector._sessions

    # Also test get_active_alerts pruning empty sessions
    detector.record_usage("session-expired-2", 500, timestamp=now - 20.0)
    assert "session-expired-2" in detector._sessions
    alerts = detector.get_active_alerts()
    assert len(alerts) == 0
    assert "session-expired-2" not in detector._sessions
