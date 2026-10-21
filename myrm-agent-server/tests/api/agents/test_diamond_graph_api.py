"""API integration tests for Diamond Topology Orchestrator & Blinded Adversarial Auditor (Item 71).

[INPUT]
- app.api.agents.diamond_graph_router.router
- app.services.agent.diamond_graph_service.get_diamond_graph_service

[OUTPUT]
- Pytest assertions verifying 3-stage Diamond DAG, False-Dependency Pruning,
  Dead-Node Census Sentinel, Deterministic 0-Token Reduce, Top-Tier Synthesis,
  and Blinded Adversarial Review with immutable Reality Anchors.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_diamond_graph_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.diamond_graph_router import router as diamond_graph_router
from app.services.agent.diamond_graph_service import get_diamond_graph_service


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory sessions before each test."""
    service = get_diamond_graph_service()
    service.reset_session("chat-test-diamond")


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with diamond_graph_router attached."""
    app = FastAPI()
    app.include_router(diamond_graph_router)
    return TestClient(app)


def test_create_and_get_nodes_api(client: TestClient) -> None:
    """Test creating 3-tier diamond DAG and retrieving nodes with CoT masking."""
    payload = {
        "goal": "Benchmark Next-Gen Vector Storage Options",
        "fan_out_specs": [
            {"node_id": "fan-qdrant", "title": "Analyze Qdrant Performance"},
            {"node_id": "fan-milvus", "title": "Analyze Milvus Scalability"},
            {"node_id": "fan-chroma", "title": "Analyze Chroma Simplicity"},
        ],
    }
    resp = client.post("/chats/chat-test-diamond/diamond-graph/pipeline", json=payload)
    assert resp.status_code == 201
    nodes = resp.json()
    assert len(nodes) == 5  # 3 fan-out + 1 reduce + 1 synthesize

    stages = [n["stage"] for n in nodes]
    assert stages.count("fan_out") == 3
    assert stages.count("reduce") == 1
    assert stages.count("synthesize") == 1

    # Verify CoT masked by default
    get_resp = client.get("/chats/chat-test-diamond/diamond-graph/nodes")
    assert get_resp.status_code == 200
    for node in get_resp.json():
        assert node["cot_reasoning_internal"] is None


def test_prune_false_dependencies_api(client: TestClient) -> None:
    """Test static analysis pruning of artificial serialized arrows between fan-out nodes."""
    client.post(
        "/chats/chat-test-diamond/diamond-graph/pipeline",
        json={
            "goal": "Parallel Code Generation",
            "fan_out_specs": [
                {"node_id": "fan-worker-1", "title": "Worker 1"},
                {"node_id": "fan-worker-2", "title": "Worker 2"},
            ],
        },
    )

    # In service layer directly or via fake dependency, fan_nodes shouldn't depend on each other
    service = get_diamond_graph_service()
    orch, _ = service._get_bundle("chat-test-diamond")
    orch._nodes["fan-worker-2"].depends_on.append("fan-worker-1")

    # Call prune API
    prune_resp = client.post("/chats/chat-test-diamond/diamond-graph/prune")
    assert prune_resp.status_code == 200
    data = prune_resp.json()
    assert data["pruned_edges"] == [["fan-worker-1", "fan-worker-2"]]

    # Verify is_pruned set to True
    nodes_resp = client.get("/chats/chat-test-diamond/diamond-graph/nodes")
    w2 = next(n for n in nodes_resp.json() if n["node_id"] == "fan-worker-2")
    assert w2["is_pruned"] is True
    assert "fan-worker-1" not in w2["depends_on"]


def test_dispatch_and_census_sentinel_api(client: TestClient) -> None:
    """Test fan-out dispatch and census sentinel health accounting."""
    client.post(
        "/chats/chat-test-diamond/diamond-graph/pipeline",
        json={
            "goal": "Parallel Testing",
            "fan_out_specs": [
                {"node_id": "f1", "title": "F1"},
                {"node_id": "f2", "title": "F2"},
            ],
        },
    )

    disp_resp = client.post("/chats/chat-test-diamond/diamond-graph/dispatch")
    assert disp_resp.status_code == 200
    disp_data = disp_resp.json()
    assert disp_data["dispatched_count"] == 2
    assert disp_data["received_count"] == 0
    assert disp_data["is_healthy"] is False
    assert set(disp_data["missing_nodes"]) == {"f1", "f2"}

    # Complete f1 with isolated CoT
    comp_resp = client.post(
        "/chats/chat-test-diamond/diamond-graph/nodes/complete",
        json={
            "node_id": "f1",
            "output_artifact": "Result from F1 benchmark [REF-01]",
            "cot_reasoning_internal": "Secret thought: model decided branch 1 was optimal",
            "success": True,
        },
    )
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "completed"

    # Census check
    census_resp = client.get("/chats/chat-test-diamond/diamond-graph/census")
    assert census_resp.status_code == 200
    c_data = census_resp.json()
    assert c_data["dispatched_count"] == 2
    assert c_data["received_count"] == 1
    assert c_data["missing_nodes"] == ["f2"]
    assert c_data["is_healthy"] is False


def test_retry_dead_nodes_api(client: TestClient) -> None:
    """Test pinpointing missing fan-out nodes and retrying them."""
    client.post(
        "/chats/chat-test-diamond/diamond-graph/pipeline",
        json={
            "goal": "Retry Faulty Branches",
            "fan_out_specs": [
                {"node_id": "branch-dead", "title": "Dead Branch"},
            ],
        },
    )

    retry_resp = client.post("/chats/chat-test-diamond/diamond-graph/retry")
    assert retry_resp.status_code == 200
    assert retry_resp.json()["retried_nodes"] == ["branch-dead"]


def test_deterministic_reduce_and_synthesize_api(client: TestClient) -> None:
    """Test deterministic 0-token reduction and top-tier synthesis."""
    client.post(
        "/chats/chat-test-diamond/diamond-graph/pipeline",
        json={
            "goal": "Security Audit Comparison",
            "fan_out_specs": [
                {"node_id": "fan-auth", "title": "Auth Exploration"},
                {"node_id": "fan-crypto", "title": "Crypto Exploration"},
            ],
        },
    )

    # Calling reduce before nodes complete should raise 409
    fail_reduce = client.post("/chats/chat-test-diamond/diamond-graph/reduce")
    assert fail_reduce.status_code == 409

    # Complete both nodes
    client.post(
        "/chats/chat-test-diamond/diamond-graph/nodes/complete",
        json={
            "node_id": "fan-auth",
            "output_artifact": "Auth check passed\nToken expires in 3600s\nDuplicate line",
            "success": True,
        },
    )
    client.post(
        "/chats/chat-test-diamond/diamond-graph/nodes/complete",
        json={
            "node_id": "fan-crypto",
            "output_artifact": "Crypto validated: AES-256-GCM\nDuplicate line",
            "success": True,
        },
    )

    # Now execute reduce
    reduce_resp = client.post("/chats/chat-test-diamond/diamond-graph/reduce")
    assert reduce_resp.status_code == 200
    reduced_text = reduce_resp.json()["reduced_artifact"]
    assert "Auth check passed" in reduced_text
    assert "Crypto validated: AES-256-GCM" in reduced_text
    # "Duplicate line" deduplicated across branches
    assert reduced_text.count("Duplicate line") == 1

    # Execute synthesis
    synth_resp = client.post(
        "/chats/chat-test-diamond/diamond-graph/synthesize",
        json={"summary_prefix": "Executive Review Summary:\n"},
    )
    assert synth_resp.status_code == 200
    synth_text = synth_resp.json()["synthesized_artifact"]
    assert synth_text.startswith("Executive Review Summary:\n")
    assert "[End of Synthesis]" in synth_text


def test_blinded_adversarial_audit_and_reality_anchors_api(client: TestClient) -> None:
    """Test blinded multi-perspective critique and immutable external reality anchors."""
    artifact_ok = (
        "Enterprise Architecture Delivery v2.1 [SEC-01].\n"
        "Fully aligned with modern stateless concurrency patterns."
    )

    # 1. Successful audit with matching reality anchors
    anchors = [
        {
            "anchor_type": "exit_code_zero",
            "target_id": "unit_test_suite",
            "expected_value": "0",
            "actual_value": "0",
        },
        {
            "anchor_type": "hash_match",
            "target_id": "checksum_sha256",
            "expected_value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "actual_value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
    ]

    resp_pass = client.post(
        "/chats/chat-test-diamond/diamond-graph/audit",
        json={"artifact": artifact_ok, "reality_anchors": anchors, "pass_vote_ratio": 0.67},
    )
    assert resp_pass.status_code == 200
    data_pass = resp_pass.json()
    assert data_pass["passed"] is True
    assert data_pass["pass_count"] >= 2
    assert len(data_pass["reviews"]) == 3
    assert all(a["verified"] is True for a in data_pass["anchor_checks"])

    # 2. Failing audit due to reality anchor violation (e.g. exit code 1)
    bad_anchors = [
        {
            "anchor_type": "exit_code_zero",
            "target_id": "unit_test_suite",
            "expected_value": "0",
            "actual_value": "1",  # Fails!
        }
    ]
    resp_fail = client.post(
        "/chats/chat-test-diamond/diamond-graph/audit",
        json={"artifact": artifact_ok, "reality_anchors": bad_anchors, "pass_vote_ratio": 0.67},
    )
    assert resp_fail.status_code == 200
    data_fail = resp_fail.json()
    assert data_fail["passed"] is False
    assert "reality anchors violated" in data_fail["consensus_summary"]
