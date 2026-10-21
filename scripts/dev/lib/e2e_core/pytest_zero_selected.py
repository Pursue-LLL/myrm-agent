"""Detect pytest sessions that collected zero runnable tests (chrome E2E fail-fast)."""

from __future__ import annotations

import os
import re

_ZERO_SELECTED_RE = re.compile(r"\b0 selected\b")
_DESELECTED_ALL_RE = re.compile(
    r"collected \d+ item(?:s)? / \d+ deselected / 0 selected",
    re.MULTILINE,
)
_COLLECTED_ITEMS_RE = re.compile(r"collected (\d+) item(?:s)?", re.MULTILINE)
_SKIPPED_SUMMARY_RE = re.compile(r"=+ (\d+) skipped in", re.MULTILINE)


def chrome_e2e_session_active() -> bool:
    """True when ./myrm test has entered formal chrome_e2e attach."""
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    if not lease_id or lease_id == "myrm-llm-e2e-local":
        return False
    if os.environ.get("MYRM_CHROME_E2E_ATTACH", "").strip() == "1":
        return True
    return bool(os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip())


def pytest_output_zero_selected(output: str) -> bool:
    if _DESELECTED_ALL_RE.search(output):
        return True
    if _ZERO_SELECTED_RE.search(output):
        return True
    return False


def pytest_output_all_skipped(output: str) -> bool:
    """True when every collected chrome_e2e item was skipped (silent false-green)."""
    collected = _COLLECTED_ITEMS_RE.search(output)
    skipped = _SKIPPED_SUMMARY_RE.search(output)
    if collected is None or skipped is None:
        return False
    collected_count = int(collected.group(1))
    skipped_count = int(skipped.group(1))
    return collected_count > 0 and skipped_count >= collected_count


def zero_selected_exit_code(*, output: str, proc_exit_code: int) -> int:
    if not chrome_e2e_session_active():
        return proc_exit_code
    if pytest_output_all_skipped(output):
        return 5 if proc_exit_code == 0 else proc_exit_code
    if not pytest_output_zero_selected(output):
        return proc_exit_code
    return 5 if proc_exit_code == 0 else proc_exit_code
