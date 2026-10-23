"""The Agent editor's built-in subagent catalog must be metadata-only and scoped."""

from starlette.testclient import TestClient

_EXPECTED_IDS = [
    "structure-planner",
    "layout-designer",
    "format-verifier",
    "browser",
    "explore",
]


def test_list_subagent_presets_exposes_only_user_selectable_specs(client: TestClient):
    response = client.get("/api/v1/agents/subagent-presets")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    presets = body["data"]
    assert [preset["id"] for preset in presets] == _EXPECTED_IDS

    for preset in presets:
        assert preset["display_name"]
        assert preset["description"]
        assert isinstance(preset["required_builtin_tools"], list)
        assert "system_prompt" not in preset
        assert "tools" not in preset

    browser = next(preset for preset in presets if preset["id"] == "browser")
    assert browser["required_builtin_tools"] == ["browser"]


def test_adversarial_reviewer_is_internal_and_not_exposed(client: TestClient):
    response = client.get("/api/v1/agents/subagent-presets")

    assert response.status_code == 200
    ids = {preset["id"] for preset in response.json()["data"]}
    assert "adversarial-reviewer" not in ids


def test_presets_api_returns_500_when_catalog_load_fails(client: TestClient):
    from unittest.mock import patch

    with patch(
        "app.api.agents.subagent_presets.router.load_user_selectable_subagent_configs",
        side_effect=RuntimeError("catalog broken"),
    ):
        response = client.get("/api/v1/agents/subagent-presets")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == 50001
