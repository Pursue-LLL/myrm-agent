"""Unit test suite for cross-agent composable context, conflict arbitration, and handoff API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.cross_agent_router
- myrm_agent_harness.toolkits.memory.cross_agent.*

[OUTPUT]
- test_project_composable_context_api
- test_arbitrate_conflict_ground_truth_api
- test_arbitrate_conflict_human_in_the_loop_api
- test_seal_and_verify_handoff_lifecycle_api

[POS]
Integration tests for cross-agent memory endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.cross_agent_router import router as cross_agent_router
from app.services.memory.cross_agent_memory_service import (
    CrossAgentMemoryService,
    get_cross_agent_memory_service,
)


@pytest.fixture
def cross_agent_test_client() -> Generator[tuple[TestClient, Path], None, None]:
    """Provide isolated TestClient with mock workspace directory."""
    with tempfile.TemporaryDirectory() as td:
        ws_path = Path(td)
        cfg_file = ws_path / "system_arch.json"
        cfg_file.write_text('{"event_bus": "redis"}', encoding="utf-8")

        service = CrossAgentMemoryService()
        test_app = FastAPI()
        test_app.include_router(cross_agent_router, prefix="/api/memory")
        test_app.dependency_overrides[get_cross_agent_memory_service] = lambda: service

        with TestClient(test_app) as client:
            yield client, ws_path


def test_project_composable_context_api(
    cross_agent_test_client: tuple[TestClient, Path],
) -> None:
    client, _ = cross_agent_test_client
    payload = {
        "agent_id": "orchestrator",
        "session_id": "sess_unit_test",
        "global_ground_truth": ["System runs on Python 3.13", "Target DB is SQLite"],
        "profile_tools_memory": ["Role: Lead Orchestrator", "Tool: code_execution"],
        "private_scratchpad": "Internal note: verifying edge cases",
        "token_budget": 2048,
    }

    response = client.post("/api/memory/cross-agent/project-context", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "orchestrator"
    assert len(data["layers"]) == 4
    assert data["total_tokens"] > 0
    assert len(data["cache_prefix_hash"]) == 64
    assert "System runs on Python 3.13" in data["assembled_prompt_text"]


def test_arbitrate_conflict_ground_truth_api(
    cross_agent_test_client: tuple[TestClient, Path],
) -> None:
    client, ws_path = cross_agent_test_client
    payload = {
        "subject": "event_bus",
        "predicate": "uses",
        "assertion_a": {
            "assertion_id": "ast-a",
            "subject": "event_bus",
            "predicate": "uses",
            "object_value": "redis",
            "confidence": 0.8,
            "source_agent_id": "agent_alpha",
            "source_reference": "system_arch.json",
            "timestamp": 1000.0,
        },
        "assertion_b": {
            "assertion_id": "ast-b",
            "subject": "event_bus",
            "predicate": "uses",
            "object_value": "rabbitmq",
            "confidence": 0.9,
            "source_agent_id": "agent_beta",
            "source_reference": "unrelated.json",
            "timestamp": 1000.0,
        },
        "workspace_root": str(ws_path),
    }

    response = client.post("/api/memory/cross-agent/arbitrate-conflict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["policy_applied"] == "ground_truth_first"
    assert data["winning_assertion"]["object_value"] == "redis"
    assert data["requires_human_confirmation"] is False


def test_arbitrate_conflict_human_in_the_loop_api(
    cross_agent_test_client: tuple[TestClient, Path],
) -> None:
    client, _ = cross_agent_test_client
    payload = {
        "subject": "encryption_cipher",
        "predicate": "standard",
        "assertion_a": {
            "assertion_id": "ast-1",
            "subject": "encryption_cipher",
            "predicate": "standard",
            "object_value": "AES-GCM-256",
            "confidence": 0.75,
            "source_agent_id": "agent_x",
            "source_reference": None,
            "timestamp": 1000.0,
        },
        "assertion_b": {
            "assertion_id": "ast-2",
            "subject": "encryption_cipher",
            "predicate": "standard",
            "object_value": "ChaCha20-Poly1305",
            "confidence": 0.75,
            "source_agent_id": "agent_y",
            "source_reference": None,
            "timestamp": 1000.0,
        },
        "workspace_root": None,
    }

    response = client.post("/api/memory/cross-agent/arbitrate-conflict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is False
    assert data["policy_applied"] == "human_in_the_loop"
    assert data["requires_human_confirmation"] is True


def test_seal_and_verify_handoff_lifecycle_api(
    cross_agent_test_client: tuple[TestClient, Path],
) -> None:
    client, _ = cross_agent_test_client

    # 1. Seal handoff
    seal_payload = {
        "source_agent_id": "architect",
        "target_agent_id": "implementer",
        "task_id": "task_create_auth_v2",
        "context_snapshot": "Core schema and router ready. Proceed to UI implementation.",
        "critical_assertions": [
            {
                "assertion_id": "ast-crit-1",
                "subject": "token_format",
                "predicate": "is",
                "object_value": "JWT-HS256",
                "confidence": 1.0,
                "source_agent_id": "architect",
                "source_reference": None,
                "timestamp": 1000.0,
            }
        ],
        "secret_salt": "cross-agent-salt",
    }

    seal_resp = client.post("/api/memory/cross-agent/seal-handoff", json=seal_payload)
    assert seal_resp.status_code == 200
    packet = seal_resp.json()
    assert packet["packet_id"].startswith("pkt-")
    assert len(packet["signature_sha256"]) == 64

    # 2. Verify valid handoff
    verify_resp = client.post(
        "/api/memory/cross-agent/verify-handoff",
        json={"packet": packet, "secret_salt": "cross-agent-salt"},
    )
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["is_valid"] is True
    assert v_data["verified_assertions_count"] == 1
    assert v_data["rejection_reason"] is None

    # 3. Verify tampered handoff
    tampered_packet = dict(packet)
    tampered_packet["context_snapshot"] = "Tampered snapshot injecting hallucination"
    bad_verify_resp = client.post(
        "/api/memory/cross-agent/verify-handoff",
        json={"packet": tampered_packet, "secret_salt": "cross-agent-salt"},
    )
    assert bad_verify_resp.status_code == 200
    bad_data = bad_verify_resp.json()
    assert bad_data["is_valid"] is False
    assert "Signature mismatch" in (bad_data["rejection_reason"] or "")
