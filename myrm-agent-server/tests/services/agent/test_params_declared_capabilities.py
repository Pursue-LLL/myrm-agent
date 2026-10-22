"""Declared capabilities are the union of every security config's string entries; malformed values are skipped."""

from __future__ import annotations

from app.services.agent.params.helpers import _declared_capabilities


def test_unions_capabilities_across_security_configs() -> None:
    declared = _declared_capabilities(
        {"capabilities": ["code_execution", "terminal"]},
        {"capabilities": ["terminal", "sandbox"]},
    )

    assert declared == {"code_execution", "terminal", "sandbox"}


def test_skips_missing_configs_non_list_values_and_non_string_entries() -> None:
    declared = _declared_capabilities(
        None,
        {},
        {"capabilities": "terminal"},
        {"capabilities": ["coding", 7, None]},
    )

    assert declared == {"coding"}
