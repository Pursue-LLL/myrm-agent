"""Text typed into the agent editor, the AI builders, a batch run or a skill derivation is read by a model: a secret in it is refused first.

Runs the real route handlers; only the detection rules and what lies behind the gate are injected. A refusal is HTTP 400
with the ``risk_held`` code and the matched rules, and nothing is stored or sent to a model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from app.api.agents.agent import router as agent_router
from app.api.agents.ai_build import router as ai_build_router
from app.api.agents.generate_prompt import router as generate_prompt_router
from app.api.batch_directory.router import router as batch_router
from app.api.skills.evolution.derive import router as derive_router
from app.database.connection import get_db
from app.services.risk.refusal import RISK_HELD_CODE
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

_DETECTION = "app.services.risk.detection.get_detection_service"


@pytest.fixture(autouse=True)
def _risk_rules() -> Iterator[None]:
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(agent_router, prefix="/user-agents")
    app.include_router(generate_prompt_router, prefix="/user-agents")
    app.include_router(ai_build_router, prefix="/user-agents")
    app.include_router(batch_router)
    app.include_router(derive_router, prefix="/skills/evolution")
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as test_client:
        yield test_client


def _assert_held(response: Response) -> None:
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == RISK_HELD_CODE
    assert detail["rules"] == [{"rule_id": "r-apikey", "display_name": "API Key Leak", "severity": "critical"}]
    assert SECRET not in response.text


async def _empty_stream() -> AsyncIterator[str]:
    for chunk in ():
        yield chunk


# --- agent profile -----------------------------------------------------------------------------------------------


@pytest.fixture
def agent_service() -> Iterator[MagicMock]:
    service = MagicMock()
    service.create_agent = AsyncMock(return_value=SimpleNamespace())
    service.get_agent_by_id = AsyncMock(return_value=SimpleNamespace(built_in=False))
    service.update_agent = AsyncMock(return_value=SimpleNamespace(profile=SimpleNamespace(), snapshot_saved=False))
    service.count_profile_snapshots = AsyncMock(return_value=0)
    response = MagicMock()
    response.model_dump.return_value = {}
    with (
        patch("app.api.agents.agent.AgentService", service),
        patch("app.api.agents.agent._to_agent_response", return_value=response),
    ):
        yield service


_PROFILE_TEXT = {
    "system_prompt": {"system_prompt": f"log in to the mailbox with {SECRET}"},
    "description": {"description": f"works with {SECRET}"},
    "suggestion_prompts": {"suggestion_prompts": ["summarise the inbox", f"use {SECRET}"]},
    "command_binding_instruction": {
        "command_bindings": [{"command_name": "daily", "instruction": f"call the API with {SECRET}"}],
    },
}


@pytest.mark.parametrize("fields", _PROFILE_TEXT.values(), ids=_PROFILE_TEXT.keys())
def test_agent_create_with_a_secret_is_refused_and_not_stored(
    client: TestClient, agent_service: MagicMock, fields: dict[str, object]
) -> None:
    _assert_held(client.post("/user-agents", json={"name": "helper", **fields}))

    agent_service.create_agent.assert_not_awaited()


@pytest.mark.parametrize("fields", _PROFILE_TEXT.values(), ids=_PROFILE_TEXT.keys())
def test_agent_update_with_a_secret_is_refused_and_unchanged(
    client: TestClient, agent_service: MagicMock, fields: dict[str, object]
) -> None:
    _assert_held(client.put("/user-agents/agent-1", json=fields))

    agent_service.update_agent.assert_not_awaited()


def test_agent_with_clean_text_is_stored(client: TestClient, agent_service: MagicMock) -> None:
    body = {
        "name": "helper",
        "system_prompt": "You summarise the inbox.",
        "suggestion_prompts": ["summarise the inbox"],
        "command_bindings": [{"command_name": "daily", "instruction": "list today's mail"}],
    }

    assert client.post("/user-agents", json=body).status_code == 200
    assert client.put("/user-agents/agent-1", json=body).status_code == 200

    agent_service.create_agent.assert_awaited_once()
    agent_service.update_agent.assert_awaited_once()


def test_agent_update_without_text_is_not_screened(client: TestClient, agent_service: MagicMock) -> None:
    assert client.put("/user-agents/agent-1", json={"name": "renamed"}).status_code == 200

    agent_service.update_agent.assert_awaited_once()


# --- AI builders -------------------------------------------------------------------------------------------------


_PROMPT_BODIES = {
    "intent": {"intent": f"an agent that logs in with {SECRET}"},
    "current_prompt": {"intent": "a writing coach", "current_prompt": f"password {SECRET}"},
}


@pytest.mark.parametrize("body", _PROMPT_BODIES.values(), ids=_PROMPT_BODIES.keys())
def test_generate_prompt_with_a_secret_never_reaches_the_model(client: TestClient, body: dict[str, str]) -> None:
    with patch("app.api.agents.generate_prompt.generate_prompt_stream") as stream:
        _assert_held(client.post("/user-agents/generate-prompt", json=body))

    stream.assert_not_called()


def test_generate_prompt_with_clean_text_streams(client: TestClient) -> None:
    with (
        patch("app.api.agents.generate_prompt.load_user_configs", AsyncMock(return_value=None)),
        patch("app.api.agents.generate_prompt.resolve_model_config"),
        patch("app.api.agents.generate_prompt.generate_prompt_stream", return_value=_empty_stream()) as stream,
    ):
        response = client.post("/user-agents/generate-prompt", json={"intent": "a writing coach", "current_prompt": "be kind"})

    assert response.status_code == 200
    stream.assert_called_once()


def test_ai_build_with_a_secret_never_reaches_the_model(client: TestClient) -> None:
    with patch("app.api.agents.ai_build._ai_build_stream") as stream:
        _assert_held(client.post("/user-agents/ai-build", json={"intent": f"an agent that uses {SECRET}"}))

    stream.assert_not_called()


def test_ai_build_with_clean_text_streams(client: TestClient) -> None:
    with (
        patch("app.api.agents.ai_build.load_user_configs", AsyncMock(return_value=None)),
        patch("app.api.agents.ai_build.resolve_model_config"),
        patch("app.api.agents.ai_build._ai_build_stream", return_value=_empty_stream()) as stream,
    ):
        response = client.post("/user-agents/ai-build", json={"intent": "an agent that tracks invoices"})

    assert response.status_code == 200
    stream.assert_called_once()


# --- batch run and skill derivation ------------------------------------------------------------------------------


def _batch(prompt: str) -> dict[str, object]:
    return {"name": "rename", "prompt": prompt, "directories": ["/tmp/a"]}


def test_batch_prompt_with_a_secret_never_reaches_the_service(client: TestClient) -> None:
    service = MagicMock()
    service.create_project = AsyncMock()

    with patch("app.api.batch_directory.router._svc", return_value=service):
        _assert_held(client.post("/batch-directories", json=_batch(f"upload with {SECRET}")))

    service.create_project.assert_not_awaited()


def test_batch_with_a_clean_prompt_reaches_the_service(client: TestClient) -> None:
    service = MagicMock()
    service.create_project = AsyncMock(side_effect=ValueError("directory is not allowed"))

    with patch("app.api.batch_directory.router._svc", return_value=service):
        response = client.post("/batch-directories", json=_batch("rename the files"))

    assert response.status_code == 400
    assert response.json()["detail"] == "directory is not allowed"
    service.create_project.assert_awaited_once()


@pytest.fixture
def evolution_engine() -> Iterator[MagicMock]:
    """The engine lookup, which a request reaches only after the gate; it reports no engine so no derivation runs."""
    store = MagicMock()
    store.get_skill.return_value = SimpleNamespace(name="report")
    lookup = MagicMock(return_value=None)
    with (
        patch("app.api.skills.evolution.derive._get_skill_store", return_value=store),
        patch("myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration", lookup),
    ):
        yield lookup


def test_skill_derivation_with_a_secret_never_reaches_the_engine(client: TestClient, evolution_engine: MagicMock) -> None:
    _assert_held(client.post("/skills/evolution/derive/skill-1", json={"instruction": f"call it with {SECRET}"}))

    evolution_engine.assert_not_called()


def test_skill_derivation_with_a_clean_instruction_reaches_the_engine(client: TestClient, evolution_engine: MagicMock) -> None:
    response = client.post("/skills/evolution/derive/skill-1", json={"instruction": "also cover the 2026 rows"})

    assert response.status_code == 503
    evolution_engine.assert_called_once()
