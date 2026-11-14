"""Golden request test: the transport sends what the baseline client library sent, except where registered.

[INPUT]
- golden_capture (POS: scenario matrix recorder)
- golden_baseline.json (POS: requests recorded from the baseline client library)
- golden_catalog.json (POS: the model facts the baseline was recorded with, pinned so a catalog refresh cannot move them)
- golden_allowed / golden_bedrock_allowed (POS: registries of intentional differences)

[OUTPUT]
- tests that fail on any unregistered difference and on any registry rule that matches nothing

[POS]
Safety net for replacing the LLM client library: every provider, a model of each capability family and the strict
histories (see ``golden_capture``), compared field by field on the final HTTP request.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.llms.catalog import store

from .golden_capture import capture_all, install_recorder
from .golden_diff import CHAT_RULES, diff_case, explain

_BASELINE = Path(__file__).parent / "golden_baseline.json"
_CATALOG = Path(__file__).parent / "golden_catalog.json"


@pytest.fixture(scope="module")
def comparison(monkeypatch_module: pytest.MonkeyPatch) -> tuple[dict[str, list[str]], Counter[str]]:
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    baseline.pop("_meta")
    pinned = json.loads(_CATALOG.read_text(encoding="utf-8"))
    monkeypatch_module.setattr(store, "_snapshot", lambda: pinned)
    for region in ("AWS_REGION_NAME", "AWS_REGION", "AWS_DEFAULT_REGION"):  # the default endpoint's region
        monkeypatch_module.delenv(region, raising=False)
    store._snapshot_by_lowercase.cache_clear()  # derived from the snapshot: must not keep the pinned subset
    current = capture_all(install_recorder(monkeypatch_module))
    assert set(current) == set(baseline), "the scenario matrix changed: re-record the baseline"
    unexplained: dict[str, list[str]] = {}
    used: Counter[str] = Counter()
    for case, recorded in baseline.items():
        matched, leftover = explain(case, diff_case(recorded, current[case]))
        used.update(matched)
        if leftover:
            unexplained[case] = [f"{d.kind} {d.path}: {d.old!r} -> {d.new!r}"[:240] for d in leftover]
    return unexplained, used


@pytest.fixture(scope="module")
def monkeypatch_module() -> Iterator[pytest.MonkeyPatch]:
    with pytest.MonkeyPatch.context() as patch:
        yield patch
    store._snapshot_by_lowercase.cache_clear()


def test_every_difference_is_registered(comparison: tuple[dict[str, list[str]], Counter[str]]) -> None:
    unexplained, _ = comparison
    report = "\n".join(f"{case}\n  " + "\n  ".join(items) for case, items in unexplained.items())
    assert not unexplained, f"{len(unexplained)} cases differ from the baseline without a registered reason:\n{report}"


def test_registry_has_no_stale_rules(comparison: tuple[dict[str, list[str]], Counter[str]]) -> None:
    _, used = comparison
    stale = [rule.id for rule in CHAT_RULES if rule.id not in used]
    assert not stale, f"registered differences that no longer occur: {stale}"
