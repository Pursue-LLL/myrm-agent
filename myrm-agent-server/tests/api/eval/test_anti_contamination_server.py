"""Tests for Server Layer Anti-Contamination and Canary Integrations."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.eval import CANARY_GUID

from app.core.eval.benchmarks import list_benchmark_sources
from app.core.eval.executor import LocalEvalExecutor
from tests.support.minimal_app import build_minimal_app


def test_executor_benchmark_mode_auto_injects_canary_into_blocked_terms():
    # 1. Non-benchmark mode without blocked terms
    executor_normal = LocalEvalExecutor(benchmark_mode=False)
    assert executor_normal._blocked_terms is None

    # 2. Benchmark mode automatically includes CANARY_GUID
    executor_bench = LocalEvalExecutor(benchmark_mode=True)
    assert executor_bench._blocked_terms is not None
    assert CANARY_GUID in executor_bench._blocked_terms

    # 3. Benchmark mode with custom blocked terms preserves them and appends CANARY_GUID
    executor_custom = LocalEvalExecutor(
        benchmark_mode=True,
        blocked_terms=("secret_term_123",),
    )
    assert executor_custom._blocked_terms is not None
    assert "secret_term_123" in executor_custom._blocked_terms
    assert CANARY_GUID in executor_custom._blocked_terms


def test_benchmark_sources_canary_protection_metadata():
    sources = list_benchmark_sources()
    source_map = {str(s["benchmark_id"]): s for s in sources}

    assert "browsecomp" in source_map
    assert source_map["browsecomp"].get("canary_protected") is True

    assert "operational-assurance" in source_map
    assert source_map["operational-assurance"].get("canary_protected") is True


@pytest.mark.asyncio
async def test_anti_contamination_api_endpoints():
    app = build_minimal_app(preset="eval")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Embed canary
        raw_content = '{"cases": [{"message": "solve test task"}]}'
        resp = await client.post(
            "/api/v1/eval/anti-contamination/embed-canary",
            json={"content": raw_content},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert CANARY_GUID in data["protected_content"]
        assert data["canary_guid"] == CANARY_GUID

        # 2. Audit protected content
        resp_audit = await client.get("/api/v1/eval/anti-contamination/audit")
        assert resp_audit.status_code == 200
        audit_data = resp_audit.json()
        assert "is_protected" in audit_data
        assert "canary_guid" in audit_data
        assert audit_data["canary_guid"] == CANARY_GUID
