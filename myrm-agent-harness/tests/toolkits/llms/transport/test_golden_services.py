"""Golden services test: embedding, rerank, image and web-search calls match the baseline client library, except where registered.

[INPUT]
- golden_services (POS: scenario matrix recorder for the four service paths)
- golden_services_baseline.json (POS: requests, results and failure kinds recorded from the baseline client library)
- golden_services_allowed (POS: registry of intentional differences)

[OUTPUT]
- tests that fail on any unregistered difference and on any registry rule that matches nothing

[POS]
Safety net for replacing the LLM client library on the non-chat paths: 4 service families x providers x scenarios,
compared field by field on the final HTTP request plus the decoded result and the failure kind.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from .golden_diff import diff_service_case, explain
from .golden_services import capture_services
from .golden_services_allowed import SERVICE_RULES

_BASELINE = Path(__file__).parent / "golden_services_baseline.json"


@pytest.fixture(scope="module")
def comparison() -> tuple[dict[str, list[str]], Counter[str]]:
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    baseline.pop("_meta")
    with pytest.MonkeyPatch.context() as patch:
        current = capture_services(patch)
    assert set(current) == set(baseline), "the scenario matrix changed: re-record the baseline"
    unexplained: dict[str, list[str]] = {}
    used: Counter[str] = Counter()
    for case, recorded in baseline.items():
        matched, leftover = explain(case, diff_service_case(recorded, current[case]), SERVICE_RULES)
        used.update(matched)
        if leftover:
            unexplained[case] = [f"{d.kind} {d.path}: {d.old!r} -> {d.new!r}"[:240] for d in leftover]
    return unexplained, used


def test_every_difference_is_registered(comparison: tuple[dict[str, list[str]], Counter[str]]) -> None:
    unexplained, _ = comparison
    report = "\n".join(f"{case}\n  " + "\n  ".join(items) for case, items in unexplained.items())
    assert not unexplained, f"{len(unexplained)} cases differ from the baseline without a registered reason:\n{report}"


def test_registry_has_no_stale_rules(comparison: tuple[dict[str, list[str]], Counter[str]]) -> None:
    _, used = comparison
    stale = [rule.id for rule in SERVICE_RULES if rule.id not in used]
    assert not stale, f"registered differences that no longer occur: {stale}"
