"""
[INPUT]
- TestClient from starlette/fastapi test suite
- Session Map API routes under /api/v1/session-map

[OUTPUT]
- Unit tests verifying session map project clusters, cockpit metrics summary, state filtering, and instant search

[POS]
Unit tests for Project-Centric Session Map and Agent State Cockpit API.
Strict typing: Zero `Any`. File length < 160 lines.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.session_map.routes import router as session_map_router


@pytest.fixture
def session_map_client() -> TestClient:
    app = FastAPI()
    app.include_router(session_map_router, prefix="/api/v1/session-map")
    return TestClient(app)


def test_list_session_map_projects(session_map_client: TestClient):
    """Test retrieving project clusters and nested session nodes."""
    response = session_map_client.get("/api/v1/session-map/projects")
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1

    first_proj = data[0]
    assert "id" in first_proj
    assert "name" in first_proj
    assert "workspace_path" in first_proj
    assert "git_repo_url" in first_proj
    assert "sessions" in first_proj
    assert isinstance(first_proj["sessions"], list)

    if first_proj["sessions"]:
        first_session = first_proj["sessions"][0]
        assert "id" in first_session
        assert "title" in first_session
        assert "state" in first_session
        assert first_session["state"] in ("working", "ready", "waiting_input", "idle", "error")
        assert "tokens_used" in first_session
        assert "last_active_at" in first_session


def test_list_session_map_projects_with_state_filter(session_map_client: TestClient):
    """Test filtering session map by agent runtime state."""
    response = session_map_client.get("/api/v1/session-map/projects?state_filter=working")
    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    for proj in data:
        for s in proj["sessions"]:
            assert s["state"] == "working"


def test_get_fleet_cockpit_summary(session_map_client: TestClient):
    """Test retrieving global cockpit metrics across projects and agents."""
    response = session_map_client.get("/api/v1/session-map/cockpit")
    assert response.status_code == 200
    data = response.json()

    assert "total_projects" in data
    assert "total_sessions" in data
    assert "total_agents" in data
    assert "working_agents" in data
    assert "ready_agents" in data
    assert "total_tokens_consumed" in data
    assert "top_active_sessions" in data
    assert isinstance(data["top_active_sessions"], list)


def test_search_session_map_title_match(session_map_client: TestClient):
    """Test searching session nodes by title keyword."""
    payload = {
        "query": "Architecture",
    }
    response = session_map_client.post("/api/v1/session-map/search", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["query"] == "Architecture"
    assert "total_hits" in data
    assert "hits" in data
    assert isinstance(data["hits"], list)

    if data["total_hits"] > 0:
        hit = data["hits"][0]
        assert "session" in hit
        assert "project_name" in hit
        assert "relevance_score" in hit
        assert "matched_snippet" in hit
        assert hit["relevance_score"] > 0.0


def test_search_session_map_tag_match(session_map_client: TestClient):
    """Test searching session nodes by tag keyword."""
    payload = {
        "query": "security",
    }
    response = session_map_client.post("/api/v1/session-map/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "hits" in data


def test_search_session_map_no_match(session_map_client: TestClient):
    """Test search with unmatched query returns zero hits."""
    payload = {
        "query": "nonexistent_query_xyz_999999",
    }
    response = session_map_client.post("/api/v1/session-map/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_hits"] == 0
    assert data["hits"] == []
