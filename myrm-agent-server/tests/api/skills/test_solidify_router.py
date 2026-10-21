import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.solidify_router import router as solidify_router
from app.services.skills.solidify import SkillSolidifyService


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated FastAPI client with solidify router mounted."""
    app = FastAPI(title="Solidify Test App")
    app.include_router(solidify_router, prefix="/api/v1/skills")
    return TestClient(app)


def test_solidify_skill_heuristic_extraction(client: TestClient) -> None:
    """Solidify HTML artifact with automatic heuristic parameter minimization."""
    SkillSolidifyService.reset_instance()

    html_content = (
        "<!DOCTYPE html><html><head><title>Quantum Computing 101</title></head>"
        "<body><h1>Quantum Entanglement Explained</h1>"
        "<p>Detailed interactive slides with diagrams.</p></body></html>"
    )

    payload = {
        "name": "quantum-courseware",
        "display_title": "Quantum Courseware Generator",
        "description": "Interactive slides and visualizations for physics teaching",
        "category": "education",
        "source_artifact_content": html_content,
        "source_artifact_type": "html",
        "include_plan_before_execute_hint": True,
    }

    response = client.post("/api/v1/skills/solidify", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["name"] == "quantum-courseware"
    assert data["display_title"] == "Quantum Courseware Generator"
    assert len(data["parameters"]) >= 1

    param_names = [p["name"] for p in data["parameters"]]
    assert "topic" in param_names

    # Check generated files in the bundle
    assert "SKILL.md" in data["bundle_files"]
    assert "assets/template.html" in data["bundle_files"]
    assert "assets/example.html" in data["bundle_files"]
    assert data["preview_url"] is not None


def test_solidify_skill_custom_parameters(client: TestClient) -> None:
    """Solidify skill with explicit dynamic parameters provided by user."""
    SkillSolidifyService.reset_instance()

    html_content = "<div><span>{{speaker}}</span> will present on <span>{{subject}}</span></div>"

    payload = {
        "name": "conference-badge",
        "display_title": "Conference Badge Creator",
        "description": "Custom conference attendee badge",
        "category": "design",
        "source_artifact_content": html_content,
        "source_artifact_type": "html",
        "custom_parameters": [
            {
                "name": "speaker",
                "description": "Name of the keynote speaker",
                "default_value": "Dr. Alice",
                "placeholder_pattern": "{{speaker}}",
                "required": True,
            },
            {
                "name": "subject",
                "description": "Keynote presentation topic",
                "default_value": "AI Agents",
                "placeholder_pattern": "{{subject}}",
                "required": True,
            },
        ],
        "include_plan_before_execute_hint": False,
    }

    response = client.post("/api/v1/skills/solidify", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert len(data["parameters"]) == 2
    param_map = {p["name"]: p for p in data["parameters"]}
    assert "speaker" in param_map
    assert "subject" in param_map
    assert param_map["speaker"]["default_value"] == "Dr. Alice"


def test_clean_preview_lifecycle_and_security_headers(client: TestClient) -> None:
    """Create isolated clean preview and verify response headers preventing iframe breakage."""
    SkillSolidifyService.reset_instance()

    preview_payload = {
        "content": "<!DOCTYPE html><html><body><h1>Safe Real Browser Preview</h1></body></html>",
        "content_type": "text/html",
        "title": "Interactive Physics Lab",
    }

    # 1. Register clean preview
    reg_res = client.post("/api/v1/skills/solidify/preview", json=preview_payload)
    assert reg_res.status_code == 201
    meta = reg_res.json()
    preview_id = meta["preview_id"]
    assert preview_id.startswith("prev-")
    assert meta["view_url"] == f"/api/v1/skills/solidify/preview/{preview_id}"

    # 2. Fetch clean preview page
    view_res = client.get(meta["view_url"])
    assert view_res.status_code == 200
    assert "Safe Real Browser Preview" in view_res.text
    assert "text/html" in view_res.headers["content-type"]

    # 3. Verify CSP and Referrer-Policy headers to eliminate broken images & iframe restrictions
    assert view_res.headers.get("referrer-policy") == "no-referrer"
    csp = view_res.headers.get("content-security-policy", "")
    assert "default-src *" in csp
    assert "'unsafe-inline'" in csp


def test_clean_preview_not_found(client: TestClient) -> None:
    """Non-existent preview token returns 404."""
    response = client.get("/api/v1/skills/solidify/preview/non-existent-token")
    assert response.status_code == 404
