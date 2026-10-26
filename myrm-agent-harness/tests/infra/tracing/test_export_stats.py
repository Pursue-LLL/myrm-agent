"""What the measured export outcome says about the delivery attempts made so far."""

from __future__ import annotations

import pytest

from myrm_agent_harness.infra.tracing.otlp.stats import ExportStats


@pytest.mark.parametrize(
    ("stats", "attempted", "last_export_failed"),
    [
        (ExportStats(), False, False),
        (ExportStats(withheld_spans=3), False, False),
        (ExportStats(exported_spans=2, last_success_at=10.0), True, False),
        (ExportStats(failed_batches=1, last_failure_at=10.0), True, True),
        (ExportStats(exported_spans=2, failed_batches=1, last_success_at=10.0, last_failure_at=20.0), True, True),
        (ExportStats(exported_spans=3, failed_batches=1, last_success_at=30.0, last_failure_at=20.0), True, False),
    ],
)
def test_a_delivery_counts_as_attempted_whatever_its_outcome(
    stats: ExportStats, attempted: bool, last_export_failed: bool
) -> None:
    assert stats.attempted is attempted
    assert stats.last_export_failed is last_export_failed
