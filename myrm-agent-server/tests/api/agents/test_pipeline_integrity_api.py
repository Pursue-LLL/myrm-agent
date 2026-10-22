"""Unit tests for Pipeline Integrity & Handoff Gap Doctor API (Item 53).

[INPUT]
- app.api.agents.pipeline_integrity_router.router
- app.services.agent.pipeline_integrity_service.PipelineIntegrityService

[OUTPUT]
- Pytest test cases validating pipeline linting, gap diagnostics, auto-healing,
  inspectable decision chain extraction, and report caching.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_pipeline_integrity_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.pipeline_integrity_router import (
    get_service,
)
from app.api.agents.pipeline_integrity_router import (
    router as pipeline_integrity_router,
)
from app.services.agent.pipeline_integrity_service import (
    PipelineIntegrityService,
)


@pytest.fixture
def service() -> PipelineIntegrityService:
    PipelineIntegrityService.reset_instance()
    return PipelineIntegrityService.get_instance()


@pytest.fixture
def client(
    service: PipelineIntegrityService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(pipeline_integrity_router)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_lint_healthy_pipeline_api(client: TestClient) -> None:
    """Verifies lint endpoint on a fully compliant pipeline returns is_healthy=True."""
    payload = {
        "pipeline": {
            "pipeline_id": "api-healthy-pipe",
            "name": "API Healthy Pipeline",
            "steps": [
                {
                    "step_id": "s-route",
                    "stage": "routing",
                    "agent_role": "orchestrator",
                },
                {
                    "step_id": "s-exec",
                    "stage": "execution",
                    "agent_role": "coder",
                    "requires_verification": True,
                    "metadata": {
                        "source_agent": "orchestrator",
                        "target_agent": "coder",
                        "transfer_reason": "Code the feature",
                        "context_keys": ["spec"],
                    },
                },
                {
                    "step_id": "s-review",
                    "stage": "review",
                    "agent_role": "reviewer",
                    "requires_approval": True,
                    "metadata": {
                        "source_agent": "coder",
                        "target_agent": "reviewer",
                        "transfer_reason": "Review changes",
                        "context_keys": ["diff"],
                    },
                },
                {
                    "step_id": "s-deliver",
                    "stage": "delivery",
                    "agent_role": "deployer",
                    "produced_artifacts": ["pkg_v1.tar.gz"],
                    "metadata": {
                        "source_agent": "reviewer",
                        "target_agent": "deployer",
                        "transfer_reason": "Deploy artifact",
                        "context_keys": ["tarball"],
                    },
                },
            ],
            "version": "1.0.0",
        }
    }

    res = client.post("/agents/pipeline-integrity/lint", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["pipeline_id"] == "api-healthy-pipe"
    assert data["total_steps"] == 4
    assert data["is_healthy"] is True
    assert len(data["gaps"]) == 0
    assert len(data["decision_chain"]) == 4


def test_lint_gapped_pipeline_api(client: TestClient) -> None:
    """Verifies lint endpoint flags metadata and approval gaps on flawed pipeline."""
    payload = {
        "pipeline": {
            "pipeline_id": "api-gapped-pipe",
            "name": "API Flawed Pipeline",
            "steps": [
                {
                    "step_id": "s1",
                    "stage": "analysis",
                    "agent_role": "architect",
                },
                {
                    "step_id": "s2",
                    "stage": "execution",
                    "agent_role": "coder",
                    # Missing metadata!
                },
                {
                    "step_id": "s3",
                    "stage": "delivery",
                    "agent_role": "deployer",
                    "requires_approval": False,  # Missing approval gate!
                    "requires_verification": False,  # Missing verification!
                    "produced_artifacts": [],  # Missing publish artifact!
                },
            ],
            "version": "0.1.0",
        }
    }

    res = client.post("/agents/pipeline-integrity/lint", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["pipeline_id"] == "api-gapped-pipe"
    assert data["is_healthy"] is False
    assert len(data["gaps"]) >= 3
    rule_ids = [g["rule_id"] for g in data["gaps"]]
    assert "RULE-001-HANDOFF-METADATA" in rule_ids
    assert "RULE-002-APPROVAL-GATE" in rule_ids
    assert "RULE-003-PUBLISH-ARTIFACT" in rule_ids


def test_get_sample_pipelines_api(client: TestClient) -> None:
    """Verifies retrieval of healthy and gapped reference sample pipelines."""
    res = client.get("/agents/pipeline-integrity/samples")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "healthy" in data
    assert "gapped" in data
    assert data["healthy"]["pipeline_id"] == "sample-healthy"
    assert data["gapped"]["pipeline_id"] == "sample-gapped"


def test_auto_heal_pipeline_api(client: TestClient) -> None:
    """Verifies auto-healing generates compliant pipeline and cures blocking errors."""
    broken_payload = {
        "pipeline": {
            "pipeline_id": "pipe-to-heal",
            "name": "Flawed Pipeline",
            "steps": [
                {
                    "step_id": "s1",
                    "stage": "execution",
                    "agent_role": "coder",
                },
                {
                    "step_id": "s2",
                    "stage": "delivery",
                    "agent_role": "deployer",
                    "produced_artifacts": [],
                },
            ],
            "version": "1.0.0",
        }
    }

    heal_res = client.post("/agents/pipeline-integrity/auto-heal", json=broken_payload)
    assert heal_res.status_code == 200
    healed_pipe = heal_res.json()["data"]
    assert "+healed" in healed_pipe["version"]

    # Now verify the healed pipeline passes lint cleanly
    lint_res = client.post("/agents/pipeline-integrity/lint", json={"pipeline": healed_pipe})
    assert lint_res.status_code == 200
    lint_data = lint_res.json()["data"]
    assert lint_data["is_healthy"] is True


def test_inspect_decision_chain_api(client: TestClient) -> None:
    """Verifies extraction of inspectable decision links."""
    payload = {
        "steps": [
            {
                "step_id": "s1",
                "stage": "routing",
                "agent_role": "router",
            },
            {
                "step_id": "s2",
                "stage": "execution",
                "agent_role": "coder",
                "metadata": {
                    "source_agent": "router",
                    "target_agent": "coder",
                    "transfer_reason": "Delegating implementation task",
                    "context_keys": ["spec"],
                },
            },
        ]
    }

    res = client.post("/agents/pipeline-integrity/inspect-chain", json=payload)
    assert res.status_code == 200
    chain = res.json()["data"]
    assert len(chain) == 2
    assert chain[0]["to_role"] == "router"
    assert chain[1]["from_role"] == "router"
    assert chain[1]["to_role"] == "coder"
    assert chain[1]["reason"] == "Delegating implementation task"


def test_get_latest_cached_report_api(client: TestClient) -> None:
    """Verifies report caching and retrieval, as well as 404 for unknown pipelines."""
    # Query non-existent
    not_found = client.get("/agents/pipeline-integrity/reports/unknown-pipe-999")
    assert not_found.status_code == 404

    # Lint to trigger cache populate
    lint_payload = {
        "pipeline": {
            "pipeline_id": "cached-pipe-01",
            "name": "Cached Pipe",
            "steps": [
                {
                    "step_id": "s1",
                    "stage": "analysis",
                    "agent_role": "analyst",
                }
            ],
            "version": "1.0.0",
        }
    }
    client.post("/agents/pipeline-integrity/lint", json=lint_payload)

    # Now query cached report
    found = client.get("/agents/pipeline-integrity/reports/cached-pipe-01")
    assert found.status_code == 200
    data = found.json()["data"]
    assert data["pipeline_id"] == "cached-pipe-01"
    assert data["total_steps"] == 1
