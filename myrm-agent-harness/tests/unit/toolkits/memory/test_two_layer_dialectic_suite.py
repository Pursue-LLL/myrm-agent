"""Unit tests for the keyword-pair dialectic reconciliation engine."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.memory.two_layer_dialectic import (
    DialecticCadenceConfig,
    DialecticPassKind,
    DialecticReconciliationEngine,
    MultiPassDialecticReconciler,
)

_POSTGRES = "We store everything in PostgreSQL"
_SQLITE = "Storage switched to SQLite"
_SYNC = "写入链路保持同步"
_ASYNC = "写入链路改为异步"


def test_package_exports_the_engine_as_the_multi_pass_reconciler() -> None:
    assert MultiPassDialecticReconciler is DialecticReconciliationEngine
    assert isinstance(MultiPassDialecticReconciler(DialecticCadenceConfig()), DialecticReconciliationEngine)


def test_inspect_conflicts_flags_opposing_keywords_across_a_pair() -> None:
    conflicts = DialecticReconciliationEngine().inspect_conflicts([_POSTGRES, _SQLITE])

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.statement_a == _POSTGRES
    assert conflict.statement_b == _SQLITE
    assert conflict.subject_domain == "Database Architecture"
    assert conflict.conflict_score == pytest.approx(0.95)


def test_inspect_conflicts_checks_every_statement_pair_in_either_keyword_order() -> None:
    statements = [_SQLITE, "no keyword here", _POSTGRES, _ASYNC, _SYNC]

    conflicts = DialecticReconciliationEngine().inspect_conflicts(statements)

    assert [(c.statement_a, c.statement_b) for c in conflicts] == [(_SQLITE, _POSTGRES), (_ASYNC, _SYNC)]


@pytest.mark.parametrize(
    "statements",
    [[], [_POSTGRES], ["采用 TypeScript strict 模式", "单文件严格小于400行"]],
)
def test_inspect_conflicts_returns_nothing_without_a_contradicting_pair(statements: list[str]) -> None:
    assert DialecticReconciliationEngine().inspect_conflicts(statements) == []


@pytest.mark.parametrize(
    ("depth", "expected"),
    [
        (0, [DialecticPassKind.INSPECTION]),
        (1, [DialecticPassKind.INSPECTION]),
        (2, [DialecticPassKind.INSPECTION, DialecticPassKind.SYNTHESIS]),
        (3, [DialecticPassKind.INSPECTION, DialecticPassKind.SYNTHESIS, DialecticPassKind.RECONCILIATION]),
        (99, [DialecticPassKind.INSPECTION, DialecticPassKind.SYNTHESIS, DialecticPassKind.RECONCILIATION]),
    ],
)
def test_reconcile_all_clamps_the_reported_passes_to_one_through_three(
    depth: int, expected: list[DialecticPassKind]
) -> None:
    results = DialecticReconciliationEngine().reconcile_all([_POSTGRES, _SQLITE], depth=depth)

    assert len(results) == 1
    assert results[0].passes_executed == expected


def test_reconcile_all_resolves_in_favour_of_the_later_statement() -> None:
    results = DialecticReconciliationEngine().reconcile_all([_POSTGRES, _SQLITE, _SYNC, _ASYNC])

    assert [(r.resolved_statement, r.superseded_statements) for r in results] == [
        (_SQLITE, [_POSTGRES]),
        (_ASYNC, [_SYNC]),
    ]
    assert "Database Architecture" in results[0].rationale
    assert "Concurrency Mode" in results[1].rationale
    assert all(0.0 < r.confidence <= 1.0 for r in results)


def test_reconcile_all_gives_each_result_its_own_pass_list() -> None:
    first, second = DialecticReconciliationEngine().reconcile_all([_POSTGRES, _SQLITE, _SYNC, _ASYNC])

    first.passes_executed.clear()

    assert second.passes_executed


def test_reconcile_all_without_conflicts_returns_nothing() -> None:
    assert DialecticReconciliationEngine().reconcile_all(["alpha", "beta"]) == []
