"""Golden shapes test: every shape of saved base URL reaches the endpoint it reached before, except where registered.

[INPUT]
- golden_shapes (POS: scenario matrix recorder for chat, embedding, rerank and image calls)
- golden_shapes_baseline.json (POS: where each call went under the previous client library)
- golden_shapes_allowed (POS: registry of intentional differences)

[OUTPUT]
- tests that fail on any unregistered difference and on any registry rule that matches nothing

[POS]
Safety net for the base URLs a settings screen lets people save (bare host, trailing slash, gateway prefix, pasted
operation URL): 23 chat providers x 12 shapes and every embedding, rerank and image entry x 7 shapes. A rule covers the
cells it names; the new endpoint of a covered cell is pinned by the unit tests of the endpoint rules themselves.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from .golden_shapes import capture_shapes
from .golden_shapes_allowed import SHAPE_RULES, ShapeRule

_BASELINE = Path(__file__).parent / "golden_shapes_baseline.json"

Comparison = tuple[dict[str, tuple[list[str], list[str]]], Counter[str]]


def _covering_rule(case: str) -> ShapeRule | None:
    provider, scenario, shape = case.split("|")
    return next(
        (
            rule
            for rule in SHAPE_RULES
            if (rule.providers is None or provider in rule.providers)
            and (rule.shapes is None or shape in rule.shapes)
            and (rule.scenarios is None or scenario in rule.scenarios)
        ),
        None,
    )


@pytest.fixture(scope="module")
def comparison() -> Comparison:
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    baseline.pop("_meta")
    current = capture_shapes()
    assert set(current) == set(baseline), "the shape matrix changed: re-record the baseline"
    unexplained: dict[str, tuple[list[str], list[str]]] = {}
    used: Counter[str] = Counter()
    for case, recorded in baseline.items():
        if recorded == current[case]:
            continue
        rule = _covering_rule(case)
        if rule is None:
            unexplained[case] = (recorded, current[case])
        else:
            used[rule.id] += 1
    return unexplained, used


def test_every_difference_is_registered(comparison: Comparison) -> None:
    unexplained, _ = comparison
    report = "\n".join(f"{case}\n  was {old}\n  now {new}" for case, (old, new) in unexplained.items())
    assert not unexplained, f"{len(unexplained)} cases reach another endpoint without a registered reason:\n{report}"


def test_registry_has_no_stale_rules(comparison: Comparison) -> None:
    _, used = comparison
    stale = [rule.id for rule in SHAPE_RULES if rule.id not in used]
    assert not stale, f"registered differences that no longer occur: {stale}"
