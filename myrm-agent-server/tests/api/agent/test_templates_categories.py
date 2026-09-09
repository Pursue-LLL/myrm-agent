"""Integration tests for agent templates catalog and categorization."""

from fastapi.testclient import TestClient


class TestAgentTemplatesCategorization:
    def test_templates_include_office_role_specialists(self, client: TestClient) -> None:
        response = client.get("/api/v1/agents/templates")
        assert response.status_code == 200
        templates = response.json()["data"]
        template_map = {t["id"]: t for t in templates}

        expected_office_ids = {
            "hr_recruiter",
            "financial_analyst",
            "growth_operator",
            "admin_specialist",
        }
        for expected_id in expected_office_ids:
            assert expected_id in template_map, f"Missing expected template: {expected_id}"
            item = template_map[expected_id]
            assert item.get("category") == "office", f"Template {expected_id} category should be 'office'"
            assert item.get("name"), f"Template {expected_id} should have localized name"
            assert item.get("description"), f"Template {expected_id} should have description"

    def test_templates_have_categories(self, client: TestClient) -> None:
        response = client.get("/api/v1/agents/templates")
        assert response.status_code == 200
        templates = response.json()["data"]
        for item in templates:
            category = item.get("category")
            assert category in ("office", "engineering", "team", "general"), (
                f"Template {item['id']} has invalid category: {category}"
            )

    def test_instantiate_hr_recruiter_template_succeeds(self, client: TestClient) -> None:
        response = client.post("/api/v1/agents/instantiate-template/hr_recruiter")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"]
        assert "office-document" in (data.get("skill_ids") or [])
