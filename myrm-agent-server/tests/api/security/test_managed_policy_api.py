"""Tests for effective managed approval policy API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.security.managed_approval_policy import (
    ManagedApprovalPolicy,
    configure_process_managed_approval_policy,
)

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="security")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_effective_managed_policy_empty(client: TestClient) -> None:
    configure_process_managed_approval_policy(ManagedApprovalPolicy.empty())
    response = client.get("/api/v1/security/managed-policy/effective")
    assert response.status_code == 200
    body = response.json()
    assert body["active"] is False
    assert body["disableYolo"] is False


def test_effective_managed_policy_active(client: TestClient) -> None:
    configure_process_managed_approval_policy(
        ManagedApprovalPolicy.from_mapping({"disableYolo": True}),
    )
    try:
        response = client.get("/api/v1/security/managed-policy/effective")
        assert response.status_code == 200
        body = response.json()
        assert body["active"] is True
        assert body["disableYolo"] is True
    finally:
        configure_process_managed_approval_policy(ManagedApprovalPolicy.empty())
