"""API: reject invalid skill_configs.instance_name on agent update."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.backends.skills.state_manager import SkillStateManager


@pytest.fixture
def state_manager(tmp_path: Path) -> SkillStateManager:
    manager = SkillStateManager(base_dir=str(tmp_path / ".myrm"))
    manager.create_instance("github", "work")
    return manager


def test_put_agent_rejects_missing_skill_instance(
    client: TestClient,
    state_manager: SkillStateManager,
) -> None:
    create_resp = client.post(
        "/api/agents",
        json={
            "name": "Skill Instance Validation Agent",
            "skill_ids": ["github"],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    agent_id = create_resp.json()["data"]["id"]

    async def _fake_skill_map() -> dict[str, str]:
        return {"github": "github"}

    with (
        patch(
            "app.core.skills.state_manager_instance.get_state_manager",
            return_value=state_manager,
        ),
        patch(
            "app.services.agent.skill_instance_resolver.build_skill_id_to_name_map",
            _fake_skill_map,
        ),
    ):
        update_resp = client.put(
            f"/api/agents/{agent_id}",
            json={
                "skill_configs": {
                    "github": {"instance_name": "missing", "is_core": True},
                },
            },
        )

    assert update_resp.status_code == 400, update_resp.text
    body = update_resp.json()
    assert "missing" in str(body).lower() or body.get("success") is False
