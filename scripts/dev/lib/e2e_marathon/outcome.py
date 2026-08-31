"""Pytest log outcome classifier for marathon ledger (SSOT)."""

from __future__ import annotations

import re

_PASS_RE = re.compile(
    r"(^|[[:space:]])[1-9][0-9]* passed([,[:space:]]|$)|PYTEST_SAFE_SUMMARY.*passed=[1-9]"
)
_FAIL_RE = re.compile(
    r"(^|[[:space:]])[1-9][0-9]* failed([,[:space:]]|$)|^=+ FAILURES|PYTEST_SAFE_SUMMARY.*failed=[1-9]"
)
_SKIP_RE = re.compile(
    r"PYTEST_SAFE_SUMMARY:.*skipped=[1-9][0-9]*|(^|[[:space:]])[1-9][0-9]* skipped([,[:space:]]|$)"
)
_INFRA_MARKERS = (
    "E2E_LAUNCH_DENIED",
    "LEASE_DENIED",
    "PLANE_DEGRADED",
    "E2E_LEASE_HEARTBEAT_FAIL",
    "CHROME_E2E_FAIL",
    "OWNER_EXITED",
    "E2E_MARATHON_EXCLUSIVE",
)


def classify_outcome(rc: int, log_text: str) -> str:
    """Return PASS | SKIP | INFRA_FAIL | FAIL."""
    if _SKIP_RE.search(log_text) and not _FAIL_RE.search(log_text):
        return "SKIP"
    if _PASS_RE.search(log_text) and not _FAIL_RE.search(log_text):
        if any(marker in log_text for marker in ("E2E_LAUNCH_DENIED", "LEASE_DENIED")):
            return "INFRA_FAIL"
        return "PASS"
    if rc == 0 and _SKIP_RE.search(log_text):
        return "SKIP"
    if any(marker in log_text for marker in _INFRA_MARKERS):
        return "INFRA_FAIL"
    if rc != 0 or _FAIL_RE.search(log_text):
        return "FAIL"
    return "FAIL"
