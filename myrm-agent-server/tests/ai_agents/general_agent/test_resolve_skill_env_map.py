"""Tests for resolve_skill_env_map self-healing env resolution.

Covers:
- Env configured under a stale storage id is remapped to the runtime name
- Env configured directly under the runtime name stays in place
- Env for uninstalled skills is pruned
- Missing backend or empty config short-circuits to the input
- Backend failure falls back to the unvalidated input
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.backends.skills.protocols import SkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.ai_agents.general_agent.config_builders import (
    build_execution_config,
    build_privacy_routing_config,
    resolve_skill_env_map,
    wrap_with_privacy_routing,
)


class _FakeSkillBackend(SkillBackend):
    """Minimal async SkillBackend double for list_skills()."""

    def __init__(self, skills: list[SkillMetadata]) -> None:
        self._skills = skills

    async def list_skills(self) -> list[SkillMetadata]:
        return list(self._skills)

    async def load_skills(self, skill_ids: list[str]) -> list[SkillMetadata]:
        return [s for s in self._skills if s.name in skill_ids]

    async def get_skill_content(self, skill_name: str) -> str:
        raise NotImplementedError

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        raise NotImplementedError


def _skill(name: str, storage_skill_id: str | None = None) -> SkillMetadata:
    return SkillMetadata(name=name, description="d", storage_skill_id=storage_skill_id)


@pytest.mark.asyncio
async def test_resolve_maps_env_to_runtime_name() -> None:
    """Installed skills are kept and keyed by their runtime name."""
    backend = _FakeSkillBackend([_skill("slack_notifier_skill", storage_skill_id="slack_skill")])
    env_vars: dict[str, dict[str, str]] = {
        "slack_skill": {"SLACK_TOKEN": "x"},  # configured under old storage id
    }

    resolved = await resolve_skill_env_map(backend, env_vars)

    assert resolved == {"slack_notifier_skill": {"SLACK_TOKEN": "x"}}


@pytest.mark.asyncio
async def test_resolve_keeps_env_when_keyed_by_runtime_name() -> None:
    """Env configured directly under the runtime name stays in place."""
    backend = _FakeSkillBackend([_skill("demo_skill")])
    env_vars: dict[str, dict[str, str]] = {"demo_skill": {"SK": "1"}}

    resolved = await resolve_skill_env_map(backend, env_vars)

    assert resolved == {"demo_skill": {"SK": "1"}}


@pytest.mark.asyncio
async def test_resolve_drops_env_for_uninstalled_skills() -> None:
    """Env configs for skills no longer installed are pruned."""
    backend = _FakeSkillBackend([_skill("demo_skill")])
    env_vars: dict[str, dict[str, str]] = {
        "demo_skill": {"SK": "1"},
        "removed_skill": {"GHOST": "1"},
    }

    resolved = await resolve_skill_env_map(backend, env_vars)

    assert resolved == {"demo_skill": {"SK": "1"}}


@pytest.mark.asyncio
async def test_resolve_keeps_empty_env_when_keyed_by_runtime_name() -> None:
    """An explicitly configured empty env dict is kept, not dropped."""
    backend = _FakeSkillBackend([_skill("demo_skill")])
    env_vars: dict[str, dict[str, str]] = {"demo_skill": {}}

    resolved = await resolve_skill_env_map(backend, env_vars)

    assert resolved == {"demo_skill": {}}


@pytest.mark.asyncio
async def test_resolve_returns_input_without_backend_or_env() -> None:
    """No backend or empty config short-circuits to the input as-is."""
    env_vars: dict[str, dict[str, str]] = {"demo_skill": {"SK": "1"}}

    assert await resolve_skill_env_map(None, env_vars) == env_vars
    assert await resolve_skill_env_map(_FakeSkillBackend([]), {}) == {}


@pytest.mark.asyncio
async def test_resolve_returns_input_on_backend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend failure falls back to the unvalidated input map."""
    backend = _FakeSkillBackend([])

    async def _boom() -> list[SkillMetadata]:
        raise RuntimeError("storage down")

    monkeypatch.setattr(backend, "list_skills", _boom)
    env_vars: dict[str, dict[str, str]] = {"demo_skill": {"SK": "1"}}

    resolved = await resolve_skill_env_map(backend, env_vars)

    assert resolved == env_vars


def test_build_privacy_routing_config_none_without_local_model() -> None:
    """Missing or empty raw config yields None (routing disabled)."""
    assert build_privacy_routing_config(None) is None
    assert build_privacy_routing_config({"other": "x"}) is None


def test_build_privacy_routing_config_full() -> None:
    """Full raw config maps onto PrivacyRoutingConfig with defaults."""
    cfg = build_privacy_routing_config(
        {
            "localModel": "local/llama",
            "localBaseUrl": "http://127.0.0.1:11434/v1",
            "localApiKey": "sk-local",
            "s2Strategy": "local",
            "s3Strategy": "block",
            "localFallback": "force_redact_cloud",
        }
    )
    assert cfg is not None
    assert cfg.local_model == "local/llama"
    assert cfg.local_base_url == "http://127.0.0.1:11434/v1"
    assert cfg.local_api_key == "sk-local"
    assert cfg.s2_strategy == "local"
    assert cfg.s3_strategy == "block"
    assert cfg.local_fallback == "force_redact_cloud"


def test_build_privacy_routing_config_applies_defaults() -> None:
    """Missing optional fields fall back to documented defaults."""
    cfg = build_privacy_routing_config({"localModel": "local/llama"})
    assert cfg is not None
    assert cfg.local_base_url is None
    assert cfg.local_api_key is None
    assert cfg.s2_strategy == "cloud_after_redact"
    assert cfg.s3_strategy == "local"
    assert cfg.local_fallback == "block"


def test_build_execution_config_none_returns_base() -> None:
    """None preference returns the base execution config unchanged."""
    from myrm_agent_harness.toolkits.code_execution.config import get_execution_config

    base = get_execution_config()
    result = build_execution_config(None)
    assert result is base


def test_build_execution_config_applies_network_preference() -> None:
    """Explicit network preference is applied on top of the base config."""
    from myrm_agent_harness.toolkits.code_execution.config import get_execution_config

    base = get_execution_config()
    for allowed in (True, False):
        result = build_execution_config(allowed)
        assert result.network.allow_network is allowed
        assert result.network.allowed_hosts == base.network.allowed_hosts
        assert result.mode == base.mode


def test_wrap_with_privacy_routing_wires_local_model() -> None:
    """PrivacyRoutingModel is built with the configured local model."""
    from myrm_agent_harness.core.security.types import PrivacyRoutingConfig

    cloud_llm = MagicMock()
    routing_config = PrivacyRoutingConfig(
        local_model="local/llama",
        local_base_url="http://127.0.0.1:11434/v1",
        local_api_key="sk-local",
    )
    fake_local_llm = MagicMock()
    fake_wrapper = MagicMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.create_litellm_model",
            return_value=fake_local_llm,
        ) as mock_create,
        patch(
            "myrm_agent_harness.toolkits.llms.routing.PrivacyRoutingModel",
            return_value=fake_wrapper,
        ),
    ):
        result = wrap_with_privacy_routing(cloud_llm, routing_config)

    assert result is fake_wrapper
    mock_create.assert_called_once_with(
        model="local/llama",
        base_url="http://127.0.0.1:11434/v1",
        api_key="sk-local",
        temperature=0.2,
        streaming=True,
    )
