"""Route-level tests for agent extras: secrets, statistics, and action-space evaluation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.api.agents import agent_extras


class _Store:
    async def get_all_secrets(self, agent_id: str) -> dict[str, str]:
        return {"API_KEY": "value"}

    async def save_secret(self, agent_id: str, key: str, value: str) -> None:
        return None

    async def delete_secret(self, agent_id: str, key: str) -> bool:
        return True


def _payload(response: JSONResponse) -> dict[str, object]:
    return json.loads(response.body)


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    record = SimpleNamespace(id="agent-1", display_name="Agent One")
    monkeypatch.setattr(agent_extras.AgentService, "get_agent_by_id", AsyncMock(return_value=record))
    return record


def test_get_secrets_returns_names(monkeypatch: pytest.MonkeyPatch, agent: SimpleNamespace) -> None:
    async def backend() -> _Store:
        return _Store()

    monkeypatch.setattr(agent_extras, "_secret_backend", backend)

    response = asyncio.run(agent_extras.get_agent_secrets("agent-1", None))  # type: ignore[arg-type]

    assert _payload(response)["data"] == [{"key_name": "API_KEY"}]


def test_create_secret_returns_the_key(monkeypatch: pytest.MonkeyPatch, agent: SimpleNamespace) -> None:
    async def backend() -> _Store:
        return _Store()

    monkeypatch.setattr(agent_extras, "_secret_backend", backend)
    request = agent_extras.AgentSecretCreate(key_name="API_KEY", secret_value="value")

    response = asyncio.run(agent_extras.create_agent_secret("agent-1", request, None))  # type: ignore[arg-type]

    assert _payload(response)["data"] == {"key_name": "API_KEY"}


def test_create_secret_requires_both_fields(agent: SimpleNamespace) -> None:
    request = agent_extras.AgentSecretCreate(key_name="", secret_value="value")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_extras.create_agent_secret("agent-1", request, None))  # type: ignore[arg-type]

    assert exc.value.status_code == 400


def test_delete_secret_success(monkeypatch: pytest.MonkeyPatch, agent: SimpleNamespace) -> None:
    async def backend() -> _Store:
        return _Store()

    monkeypatch.setattr(agent_extras, "_secret_backend", backend)

    response = asyncio.run(agent_extras.delete_agent_secret("agent-1", "API_KEY", None))  # type: ignore[arg-type]

    assert response.status_code == 200


def test_delete_missing_secret_is_404(monkeypatch: pytest.MonkeyPatch, agent: SimpleNamespace) -> None:
    class _EmptyStore(_Store):
        async def delete_secret(self, agent_id: str, key: str) -> bool:
            return False

    async def backend() -> _EmptyStore:
        return _EmptyStore()

    monkeypatch.setattr(agent_extras, "_secret_backend", backend)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_extras.delete_agent_secret("agent-1", "API_KEY", None))  # type: ignore[arg-type]

    assert exc.value.status_code == 404


def test_missing_agent_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_extras.AgentService, "get_agent_by_id", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_extras.get_agent_secrets("missing", None))  # type: ignore[arg-type]

    assert exc.value.status_code == 404


class _Scalar:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one(self) -> object:
        return self._value

    def scalar_one_or_none(self) -> object:
        return self._value


class _StatsDb:
    def __init__(self) -> None:
        self._calls = 0

    async def execute(self, statement: object) -> _Scalar:
        self._calls += 1
        if self._calls == 1:
            return _Scalar(3)
        if self._calls == 2:
            return _Scalar(10)
        return _Scalar(datetime(2026, 1, 2, 3, 4, 5))


def test_statistics_reports_counts(agent: SimpleNamespace) -> None:
    response = asyncio.run(agent_extras.get_agent_statistics("agent-1", _StatsDb()))  # type: ignore[arg-type]

    data = _payload(response)["data"]
    assert data["total_sessions"] == 3
    assert data["total_messages"] == 10
    assert data["last_used_at"] == "2026-01-02T03:04:05"
    assert data["agent_name"] == "Agent One"


def test_statistics_missing_agent_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_extras.AgentService, "get_agent_by_id", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_extras.get_agent_statistics("missing", _StatsDb()))  # type: ignore[arg-type]

    assert exc.value.status_code == 404


class _Skills:
    async def get_skills_by_ids(self, skill_ids: list[str]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(id="core", description="x" * 100),
            SimpleNamespace(id="light", description=None),
        ]


def test_evaluate_action_space_scores_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.skills.store.service.skills_service", _Skills())
    monkeypatch.setattr(agent_extras, "_build_catalog_preview", AsyncMock(return_value={"inline_count": 1}))
    request = agent_extras.ActionSpaceEvalRequest(
        skill_ids=["core", "light"],
        skill_configs={"light": {"is_core": False}},
        mcp_servers=["mcp"],
        enabled_builtin_tools=["file_ops"],
    )

    response = asyncio.run(agent_extras.evaluate_action_space(request))

    data = _payload(response)["data"]
    assert data["ascs_score"] > 0
    assert data["max_safe_score"] == 1500
    assert data["catalog_preview"] == {"inline_count": 1}


def test_evaluate_action_space_failure_maps_to_500(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.skills.store.service.skills_service", _Skills())
    monkeypatch.setattr(agent_extras, "_build_catalog_preview", AsyncMock(side_effect=RuntimeError("boom")))
    request = agent_extras.ActionSpaceEvalRequest(
        skill_ids=["core"],
        skill_configs={},
        mcp_servers=[],
        enabled_builtin_tools=[],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_extras.evaluate_action_space(request))

    assert exc.value.status_code == 500


class _UserConfig:
    async def get_config(self) -> SimpleNamespace:
        return SimpleNamespace(enabled_prebuilt_ids=[])


class _Backend:
    async def load_skills(self, ids: list[str]) -> list[object]:
        return [object(), object()]


def test_catalog_preview_with_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.skills.effective_skill_ids.resolve_runtime_skill_ids",
        AsyncMock(return_value=["skill-1"]),
    )
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service",
        SimpleNamespace(storage=object(), user_config=_UserConfig()),
    )
    monkeypatch.setattr(
        "app.core.skills.loader.create_skill_backend",
        AsyncMock(return_value=_Backend()),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.runtime.catalog_display.resolve_catalog_display_skills",
        lambda skills, skill_configs: SimpleNamespace(display_skills=[1, 2], hidden_skill_count=1, overflow_count=0),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery.render_bound_skills_catalog",
        lambda skills, skill_configs: SimpleNamespace(xml="<catalog/>"),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.runtime.catalog_display.should_mount_skill_search_tool",
        lambda skills, skill_configs: True,
    )
    monkeypatch.setattr("myrm_agent_harness.utils.text_utils.get_token_count", lambda text: 7)

    preview = asyncio.run(agent_extras._build_catalog_preview(["skill-1"], {}))

    assert preview == {
        "inline_count": 2,
        "hidden_count": 1,
        "overflow_count": 0,
        "catalog_tokens": 7,
        "search_mounted": True,
    }


def test_catalog_preview_without_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.skills.effective_skill_ids.resolve_runtime_skill_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.runtime.catalog_display.resolve_catalog_display_skills",
        lambda skills, skill_configs: SimpleNamespace(display_skills=[], hidden_skill_count=0, overflow_count=0),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery.render_bound_skills_catalog",
        lambda skills, skill_configs: None,
    )

    preview = asyncio.run(agent_extras._build_catalog_preview([], {}))

    assert preview["catalog_tokens"] == 0
    assert preview["search_mounted"] is False
