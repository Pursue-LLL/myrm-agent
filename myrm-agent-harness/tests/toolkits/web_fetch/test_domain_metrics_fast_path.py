"""A domain skips the SMART fast path because networkidle was measured to fail there, never because data is missing.

``get_smart_fast_timeout`` answers "nothing learned yet" and "networkidle is unreliable" with the same
``None``. Only the second justifies abandoning the fast path, so it has its own predicate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.web_fetch.router import DomainMetricsManager
from myrm_agent_harness.toolkits.web_fetch.router.models import DomainMetrics


def _metrics(successes: int, failures: int) -> DomainMetrics:
    metrics = DomainMetrics(domain="example.com")
    for _ in range(successes):
        metrics.record_networkidle_result(success=True)
    for _ in range(failures):
        metrics.record_networkidle_result(success=False)
    return metrics


@pytest.mark.parametrize(
    ("successes", "failures", "skips"),
    [
        (0, 0, False),
        (0, 1, False),
        (0, 19, False),
        (0, 20, True),
        (9, 11, True),
        (10, 10, False),
        (20, 0, False),
    ],
    ids=["untrained", "one-failure", "19-failures", "20-failures", "45-percent", "50-percent", "all-success"],
)
def test_only_enough_failing_samples_skip_the_fast_path(successes: int, failures: int, skips: bool) -> None:
    assert _metrics(successes, failures).should_skip_smart_fast_path() is skips


def test_an_untrained_domain_learns_no_timeout_and_keeps_the_fast_path() -> None:
    metrics = _metrics(1, 0)

    assert metrics.get_smart_fast_timeout() is None
    assert metrics.should_skip_smart_fast_path() is False


def test_stats_count_a_skip_only_for_measured_unreliability(tmp_path: Path) -> None:
    manager = DomainMetricsManager(storage_path=tmp_path / "domain_metrics.json")
    healthy_without_latencies = manager.get_or_create("healthy.example")
    unreliable = manager.get_or_create("unreliable.example")
    for _ in range(25):
        healthy_without_latencies.record_networkidle_result(success=True)
        unreliable.record_networkidle_result(success=False)

    stats = manager.get_stats()

    assert stats["smart_skips"] == 1
    assert stats["smart_adjustments"] == 0
