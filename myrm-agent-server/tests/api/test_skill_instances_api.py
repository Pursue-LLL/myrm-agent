"""API integration tests for skill instance CRUD operations."""

from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def app(tmp_path: object) -> FastAPI:
    """Create minimal test app with instances API using isolated temp dir."""
    from importlib import import_module

    app = FastAPI(title="Skill Instances Test App")

    async def mock_get_deploy_identity() -> Optional[str]:
        return "test-user-id"

    pass

    from app.core.skills.state_manager_instance import init_state_manager

    init_state_manager(base_dir=str(tmp_path / "skills-test"))

    instances_module = import_module("app.api.skills.instances")
    app.include_router(instances_module.router, prefix="/api/skills", tags=["skills-instances"])

    return app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_create_instance_api(client: TestClient) -> None:
    """Test POST /api/skills/{skill}/instances endpoint."""
    response = client.post(
        "/api/skills/github_skill/instances",
        json={
            "instance_name": "test_personal",
            "env_overrides": {"GITHUB_TOKEN": "ghp_test_xxx"},
            "config_overrides": {"api_base_url": "https://api.github.com"},
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["instance_name"] == "test_personal"
    assert data["skill_name"] == "github_skill"
    assert data["env_overrides"]["GITHUB_TOKEN"] == "ghp_test_xxx"


def test_list_instances_api(client: TestClient) -> None:
    """Test GET /api/skills/{skill}/instances endpoint."""
    response = client.get("/api/skills/github_skill/instances")

    assert response.status_code == 200
    data = response.json()
    assert "instances" in data
    assert "total" in data
    assert isinstance(data["instances"], list)


def test_get_instance_api(client: TestClient) -> None:
    """Test GET /api/skills/{skill}/instances/{instance} endpoint."""
    # First create an instance
    client.post(
        "/api/skills/github_skill/instances",
        json={
            "instance_name": "test_work",
            "env_overrides": {"GITHUB_TOKEN": "ghp_work_xxx"},
        },
    )

    # Then get it
    response = client.get("/api/skills/github_skill/instances/test_work")

    assert response.status_code == 200
    data = response.json()
    assert data["instance_name"] == "test_work"
    assert data["env_overrides"]["GITHUB_TOKEN"] == "ghp_work_xxx"


def test_update_instance_api(client: TestClient) -> None:
    """Test PUT /api/skills/{skill}/instances/{instance} endpoint."""
    # First create
    client.post(
        "/api/skills/github_skill/instances",
        json={
            "instance_name": "test_update",
            "env_overrides": {"GITHUB_TOKEN": "ghp_old"},
        },
    )

    # Then update
    response = client.put(
        "/api/skills/github_skill/instances/test_update",
        json={"env_overrides": {"GITHUB_TOKEN": "ghp_new"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["env_overrides"]["GITHUB_TOKEN"] == "ghp_new"


def test_delete_instance_api(client: TestClient) -> None:
    """Test DELETE /api/skills/{skill}/instances/{instance} endpoint."""
    # First create
    client.post(
        "/api/skills/github_skill/instances",
        json={
            "instance_name": "test_delete",
            "env_overrides": {},
        },
    )

    # Then delete
    response = client.delete("/api/skills/github_skill/instances/test_delete")

    assert response.status_code == 204

    # Verify deleted
    get_response = client.get("/api/skills/github_skill/instances/test_delete")
    assert get_response.status_code == 404
