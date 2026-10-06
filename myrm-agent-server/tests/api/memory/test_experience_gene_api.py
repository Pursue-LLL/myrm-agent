"""
[POS] tests/api/memory/test_experience_gene_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.experience_gene_router
[OUTPUT] test_extract_and_record_gene_api, test_get_mutation_advice_api, test_penalize_and_stats_api
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.experience_gene_router import (
    router as experience_gene_router,
)


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting experience gene router."""
    test_app = FastAPI()
    test_app.include_router(experience_gene_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_extract_and_record_gene_api(client: TestClient) -> None:
    """Verify POST /api/memory/evolution/genes/extract endpoint."""
    payload = {
        "trace": {
            "session_id": "kernel-trace-889",
            "task_goal": "Compile and mount eBPF tracepoint driver",
            "steps": [
                {
                    "step_index": 1,
                    "tool_name": "bash",
                    "tool_input_summary": "clang -O2 -target bpf -c trace.c",
                    "tool_output_snippet": "fatal error: 'linux/bpf.h' file not found",
                    "is_failure": True,
                    "error_signature": "fatal error: 'linux/bpf.h' file not found",
                },
                {
                    "step_index": 2,
                    "tool_name": "bash",
                    "tool_input_summary": "touch linux/bpf.h",
                    "tool_output_snippet": "permission denied",
                    "is_failure": True,
                    "error_signature": "permission denied",
                },
                {
                    "step_index": 3,
                    "tool_name": "bash",
                    "tool_input_summary": "apt-get install -y linux-headers-generic",
                    "tool_output_snippet": "Installed headers",
                    "is_failure": False,
                },
            ],
            "success_verified": True,
            "final_solution_summary": "Install linux-headers-generic before compiling eBPF programs",
            "domain_tag": "kernel",
        }
    }

    resp = client.post("/api/memory/evolution/genes/extract", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["status"] == "recorded"
    gene = data["gene"]
    assert gene is not None
    assert gene["gene_id"].startswith("gene_kernel_")
    assert "tool:bash" in gene["trigger_signals"]
    assert len(gene["hypotheses_refuted"]) >= 1
    assert "linux-headers-generic" in gene["proven_resolution"]
    assert gene["proof_count"] == 1


def test_get_mutation_advice_api(client: TestClient) -> None:
    """Verify POST /api/memory/evolution/genes/advice matches active signals."""
    # First, record a gene
    trace_payload = {
        "trace": {
            "session_id": "trace-advice-1",
            "task_goal": "Resolve node heap OOM",
            "steps": [
                {
                    "step_index": 1,
                    "tool_name": "bash",
                    "tool_input_summary": "node --max-old-space-size=512 app.js",
                    "tool_output_snippet": "FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory",
                    "is_failure": True,
                    "error_signature": "JavaScript heap out of memory",
                },
                {
                    "step_index": 2,
                    "tool_name": "bash",
                    "tool_input_summary": "node --max-old-space-size=4096 app.js",
                    "tool_output_snippet": "Server listening on 3000",
                    "is_failure": False,
                },
            ],
            "success_verified": True,
            "final_solution_summary": "Scale heap limit to 4096MB or stream data in chunks",
            "domain_tag": "nodejs",
        }
    }
    client.post("/api/memory/evolution/genes/extract", json=trace_payload)

    # Query mutation advice with matching active signals
    query_payload = {
        "active_signals": ["tool:bash", "JavaScript heap out of memory"],
        "min_confidence": 0.6,
        "limit": 3,
    }
    resp = client.post("/api/memory/evolution/genes/advice", json=query_payload)
    assert resp.status_code == 200
    advice_data = resp.json()

    assert advice_data["total_matched"] >= 1
    top_advice = advice_data["advices"][0]
    assert "JavaScript heap out of memory" in top_advice["matched_signals"]
    assert len(top_advice["refuted_paths"]) >= 1
    assert "4096MB" in top_advice["recommended_resolution"]


def test_penalize_and_stats_api(client: TestClient) -> None:
    """Verify penalizing a gene and retrieving ledger statistics."""
    # Seed a gene
    trace_payload = {
        "trace": {
            "session_id": "trace-penalize-1",
            "task_goal": "Resolve CSS flexbox overflow",
            "steps": [
                {
                    "step_index": 1,
                    "tool_name": "css_edit",
                    "tool_input_summary": "display: block",
                    "tool_output_snippet": "Layout broken",
                    "is_failure": True,
                    "error_signature": "Layout broken",
                },
                {
                    "step_index": 2,
                    "tool_name": "css_edit",
                    "tool_input_summary": "min-width: 0",
                    "tool_output_snippet": "Layout fixed",
                    "is_failure": False,
                },
            ],
            "success_verified": True,
            "final_solution_summary": "Add min-width: 0 on flex children to prevent overflow",
            "domain_tag": "frontend",
        }
    }
    extract_resp = client.post("/api/memory/evolution/genes/extract", json=trace_payload)
    gene_id = extract_resp.json()["gene"]["gene_id"]

    # Check stats
    stats_resp = client.get("/api/memory/evolution/genes/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_genes"] >= 1
    assert stats["avg_confidence"] >= 0.5

    # Penalize the gene
    penalize_resp = client.post(
        "/api/memory/evolution/genes/penalize",
        json={"gene_id": gene_id, "penalty": 0.3},
    )
    assert penalize_resp.status_code == 200
    updated_gene = penalize_resp.json()
    assert updated_gene["confidence_score"] == 0.5  # 0.8 - 0.3
