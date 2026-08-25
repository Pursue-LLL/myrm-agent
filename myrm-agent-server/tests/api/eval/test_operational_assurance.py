"""Tests for Operational Assurance Audit Suite (fixtures, adapter, catalog)."""

from __future__ import annotations

import pytest

from myrm_agent_harness.eval import OperationalAssuranceCategory
from app.core.eval.benchmarks import (
    build_benchmark_cases,
    ensure_benchmark_source,
    is_known_benchmark,
    list_benchmark_sources,
)
from app.core.eval.operational_assurance import (
    OPERATIONAL_ASSURANCE_SPEC,
    build_operational_assurance_benchmark_cases,
    build_operational_assurance_cases,
    ensure_operational_assurance_source,
    list_operational_assurance_source,
)


def test_operational_assurance_fixtures_structure() -> None:
    cases, seed_map = build_operational_assurance_cases()
    assert len(cases) == 6
    categories = {c.metadata["category"] for c in cases}
    expected_categories = {
        OperationalAssuranceCategory.PERMISSION_DENIED.value,
        OperationalAssuranceCategory.TOOL_TIMEOUT.value,
        OperationalAssuranceCategory.INTERRUPTED_RECOVERY.value,
        OperationalAssuranceCategory.SANDBOX_EXHAUSTION.value,
        OperationalAssuranceCategory.SKILL_CONFLICT.value,
        OperationalAssuranceCategory.EVIDENCE_EXPIRATION.value,
    }
    assert categories == expected_categories
    assert len(seed_map) == 6


def test_operational_assurance_adapter_and_catalog() -> None:
    assert is_known_benchmark("operational-assurance")

    sources = list_benchmark_sources()
    oa_sources = [s for s in sources if s.get("benchmark_id") == "operational-assurance"]
    assert len(oa_sources) == 1
    oa_source = oa_sources[0]
    assert oa_source["name"] == "Operational Assurance Audit Suite"
    assert oa_source["task_count"] == 6
    assert oa_source["is_downloaded"] is True

    src_dir = ensure_benchmark_source("operational-assurance")
    assert src_dir.exists()

    cases, seed_map, sampled = build_benchmark_cases("operational-assurance", limit=None)
    assert len(cases) == 6
    assert sampled is False
    assert len(seed_map) == 6


def test_operational_assurance_sampling() -> None:
    cases, seed_map, sampled = build_benchmark_cases("operational-assurance", limit=3)
    assert len(cases) == 3
    assert sampled is True
    assert len(seed_map) == 3
