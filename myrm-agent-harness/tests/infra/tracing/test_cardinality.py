"""Tests for myrm_agent_harness.infra.tracing.metrics.cardinality."""

from __future__ import annotations

import ast
from pathlib import Path

from myrm_agent_harness.infra.tracing.metrics.cardinality import (
    HIGH_CARDINALITY_LABEL_BLOCKLIST,
    DynamicLabelManager,
)

_SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src" / "myrm_agent_harness"


def test_first_access_below_threshold_is_other() -> None:
    mgr = DynamicLabelManager(max_tracked=10, access_threshold=2)
    assert mgr.get_label_value("e1") == "other"


def test_reaches_threshold_tracks_entity() -> None:
    mgr = DynamicLabelManager(max_tracked=10, access_threshold=2)
    assert mgr.get_label_value("e1") == "other"
    assert mgr.get_label_value("e1") == "e1"
    assert "e1" in mgr.get_tracked_entities()


def test_exceeds_max_tracked_replaces_least_frequent() -> None:
    mgr = DynamicLabelManager(max_tracked=2, access_threshold=2)
    for _ in range(2):
        mgr.get_label_value("low_a")
    for _ in range(2):
        mgr.get_label_value("low_b")
    assert mgr.get_tracked_entities() == {"low_a", "low_b"}
    for _ in range(3):
        mgr.get_label_value("high_c")
    tracked = mgr.get_tracked_entities()
    assert "high_c" in tracked
    assert len(tracked) == 2


def test_clear_resets_state() -> None:
    mgr = DynamicLabelManager(max_tracked=5, access_threshold=2)
    mgr.get_label_value("z")
    mgr.get_label_value("z")
    mgr.clear()
    assert mgr.get_tracked_entities() == set()
    assert mgr.get_label_value("z") == "other"


def test_get_tracked_entities_returns_copy() -> None:
    mgr = DynamicLabelManager(max_tracked=10, access_threshold=1)
    mgr.get_label_value("a")
    s1 = mgr.get_tracked_entities()
    s1.add("mutated")
    s2 = mgr.get_tracked_entities()
    assert "mutated" not in s2


def _literal_instrument_attribute_keys() -> dict[str, list[str]]:
    """Attribute keys written as literals at ``instrument.add(...)`` / ``instrument.record(...)`` call sites."""
    keys: dict[str, list[str]] = {}
    for path in _SOURCE_ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"add", "record"}
            ):
                continue
            literals = [arg for arg in node.args[1:] if isinstance(arg, ast.Dict)]
            literals += [kw.value for kw in node.keywords if kw.arg == "attributes" and isinstance(kw.value, ast.Dict)]
            for literal in literals:
                for key in literal.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.setdefault(key.value, []).append(f"{path.relative_to(_SOURCE_ROOT)}:{node.lineno}")
    return keys


def test_no_instrument_records_an_unbounded_identifier_as_an_attribute() -> None:
    """One time series exists per attribute value, so an identifier-valued attribute is a memory leak by design."""
    keys = _literal_instrument_attribute_keys()
    assert {"model", "memory_type"} <= keys.keys(), "the scan must see the real attribute keys, not nothing"
    offenders = {
        key: sites for key, sites in keys.items() if key in HIGH_CARDINALITY_LABEL_BLOCKLIST or key.endswith("_id")
    }
    assert offenders == {}
