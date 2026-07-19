"""Architecture contract tests for memory brief telemetry alert rules."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_PROMETHEUS_RULES_PATH = _SERVER_ROOT / "deployments" / "prometheus" / "rules.yml"
_TARGET_ALERT = "MemoryBriefTelemetryFlushHttpErrorDetected"
_DEDUP_REJECT_ALERT = "MemoryBriefTelemetryDedupRejectDetected"


def _extract_alert_block(content: str, alert_name: str) -> str:
    match = re.search(
        rf"(?ms)^\s*- alert:\s*{re.escape(alert_name)}\n(?P<body>.*?)(?=^\s*- alert:|\Z)",
        content,
    )
    assert match is not None, f"alert block not found: {alert_name}"
    return match.group("body")


@pytest.mark.architecture
def test_memory_brief_flush_http_error_alert_uses_attempt_based_ratio_contract() -> None:
    rules_content = _PROMETHEUS_RULES_PATH.read_text(encoding="utf-8")
    block = _extract_alert_block(rules_content, _TARGET_ALERT)

    required_fragments = (
        "increase(myrm_memory_brief_status_telemetry_flush_attempts_total[10m]) >= 6",
        "increase(myrm_memory_brief_status_telemetry_flush_http_errors_total[10m])",
        "clamp_min(increase(myrm_memory_brief_status_telemetry_flush_attempts_total[10m]), 1)",
        ") >= 0.50",
        "increase(myrm_memory_brief_status_telemetry_flush_attempts_total[10m]) >= 10",
        ") >= 0.30",
        "max_over_time(myrm_memory_brief_status_telemetry_queue_fill_ratio[10m]) >= 0.60",
        "increase(myrm_memory_brief_status_telemetry_dropped_total[10m])",
        "for: 10m",
        "severity: warning",
        "ratio=errors/attempts",
    )

    for fragment in required_fragments:
        assert fragment in block, f"missing alert contract fragment: {fragment}"


@pytest.mark.architecture
def test_memory_brief_dedup_reject_alert_uses_ratio_and_redis_burst_contract() -> None:
    rules_content = _PROMETHEUS_RULES_PATH.read_text(encoding="utf-8")
    block = _extract_alert_block(rules_content, _DEDUP_REJECT_ALERT)

    required_fragments = (
        "increase(myrm_cp_memory_brief_status_events_ingested_total[10m]) >= 20",
        "increase(myrm_cp_memory_brief_status_dedup_rejected_ingested_total[10m])",
        "clamp_min(increase(myrm_cp_memory_brief_status_events_ingested_total[10m]), 1)",
        ") >= 0.05",
        "increase(myrm_cp_memory_brief_status_dedup_rejected_ingested_total[10m]) >= 5",
        'increase(myrm_cp_memory_brief_status_dedup_rejected_total{reason="redis_unavailable"}[10m]) > 0',
        "for: 10m",
        "severity: warning",
        "ratio=dedup_rejects/events",
    )

    for fragment in required_fragments:
        assert fragment in block, f"missing alert contract fragment: {fragment}"


@pytest.mark.architecture
def test_promtool_rules_check_passes_when_promtool_available() -> None:
    promtool = shutil.which("promtool")
    if promtool is None:
        if os.getenv("CI"):
            pytest.fail("promtool is required in CI for Prometheus rules semantic checks")
        pytest.skip("promtool is not installed in this environment")

    result = subprocess.run(
        [promtool, "check", "rules", str(_PROMETHEUS_RULES_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "promtool check rules failed:\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
