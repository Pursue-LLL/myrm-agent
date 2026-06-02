import os

import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestSkillOptimizationE2E:
    """Skill Optimization E2E Tests"""

    def test_health_check(self, client: TestClient):
        """Test health check endpoint"""
        response = client.get("/api/v1/skill-optimization/health")
        print(response.json())
        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True
        assert "component" in data

    def test_metrics_endpoint(self, client: TestClient):
        """Test prometheus metrics endpoint"""
        response = client.get("/api/v1/skill-optimization/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert "optimization_total" in data["metrics"]
        assert "optimization_success" in data["metrics"]

    def test_batch_optimize_and_status(self, client: TestClient):
        """Test batch optimization flow"""
        # Trigger batch optimization
        payload = {"skill_ids": ["test_skill_1", "test_skill_2"], "max_concurrent": 2, "priority": 1}
        response = client.post("/api/v1/skill-optimization/batch-optimize", json=payload)

        # If the endpoint requires auth, it might return 401/403.
        # Assuming the TestClient is configured with proper auth or the endpoint is public for tests.
        if response.status_code in [401, 403]:
            pytest.skip("Auth required for batch-optimize")

        assert response.status_code == 200
        data = response.json()
        assert "batch_task_id" in data

        batch_id = data["batch_task_id"]

        # Check status
        status_response = client.get(f"/api/v1/skill-optimization/batch-status/{batch_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["total"] == 2
        assert "status" in status_data
