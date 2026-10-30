"""PUT /skills/config: only the strategies the product offers are accepted, and a change reaches the running screener."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills import config as skills_config_api
from app.core.skills.models import UserSkillConfig

_INTEGRATION_ACCESSOR = "myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration"


class _Environment:
    def __init__(self, client: TestClient, update_config: AsyncMock, integration: MagicMock) -> None:
        self.client = client
        self.update_config = update_config
        self.integration = integration


def _updated_config(**fields: object) -> UserSkillConfig:
    return UserSkillConfig(
        user_id="u", evolution_strategy="innovate" if fields["evolution_strategy"] == "innovate" else "balanced"
    )


@pytest.fixture
def environment() -> Iterator[_Environment]:
    update_config = AsyncMock(side_effect=_updated_config)
    integration = MagicMock()
    integration.evolution_strategy = "balanced"
    app = FastAPI()
    app.include_router(skills_config_api.router, prefix="/api/v1/skills")
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                skills_config_api, "skills_service", SimpleNamespace(user_config=SimpleNamespace(update_config=update_config))
            )
        )
        stack.enter_context(patch.object(skills_config_api, "bump_skill_config_version"))
        stack.enter_context(patch(_INTEGRATION_ACCESSOR, return_value=integration))
        yield _Environment(TestClient(app), update_config, integration)


@pytest.mark.parametrize("preset", ["harden", "repair-only", "not-a-strategy"])
def test_a_strategy_the_product_does_not_offer_is_rejected(environment: _Environment, preset: str) -> None:
    response = environment.client.put("/api/v1/skills/config", json={"evolution_strategy": preset})

    assert response.status_code == 422
    environment.update_config.assert_not_awaited()
    assert environment.integration.evolution_strategy == "balanced"


def test_choosing_innovate_is_stored_and_reaches_the_running_screener(environment: _Environment) -> None:
    response = environment.client.put("/api/v1/skills/config", json={"evolution_strategy": "innovate"})

    assert response.status_code == 200
    assert response.json()["evolution_strategy"] == "innovate"
    environment.update_config.assert_awaited_once_with(
        enabled_prebuilt_ids=None, evolution_strategy="innovate", clawhub_registry_url=None
    )
    assert environment.integration.evolution_strategy == "innovate"


def test_an_update_without_a_strategy_leaves_the_running_screener_alone(environment: _Environment) -> None:
    response = environment.client.put("/api/v1/skills/config", json={"enabled_prebuilt_ids": ["data-analysis"]})

    assert response.status_code == 200
    environment.update_config.assert_awaited_once_with(
        enabled_prebuilt_ids=["data-analysis"], evolution_strategy=None, clawhub_registry_url=None
    )
    assert environment.integration.evolution_strategy == "balanced"
