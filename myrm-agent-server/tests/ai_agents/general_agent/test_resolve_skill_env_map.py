"""Tests for resolve_skill_env_map self-healing env resolution.

Covers:
- Env configured under a stale storage id is remapped to the runtime name
- Env configured directly under the runtime name stays in place
- Env for uninstalled skills is pruned
- Missing backend or empty config short-circuits to the input
- Backend failure falls back to the unvalidated input
"""

from __future__ import annotations

import pytest

from app.ai_agents.general_agent.config_builders import resolve_skill_env_map
from myrm_agent_harness.backends.skills.types_metadata import SkillMetadata


class _FakeSkillBackend:
    """Minimal async SkillBackend double for list_skills()."""

    def __init__(self, skills: list[SkillMetadata]) -> None:
        self._skills = skills

    async def list_skills(self) -> list[SkillMetadata]:
        return list(self._skills)


def _skill(name: str, storage_skill_id: str | None = None) -> SkillMetadata:
    return SkillMetadata(name=name, description="d", storage_skill_id=storage_skill_id)


@pytest.mark.asyncio
async def test_resolve_maps_env_to_runtime_name() -> None:
    """Installed skills are kept and keyed by their runtime name."""
    backend = _FakeSkillBackend(
        [_skill("slack_notifier_skill", storage_skill_id="slack_skill")]
    )
    env_vars: dict[str, dict[str, str]] = {
        "slack_skill": {"SLACK_TOKEN": "x"},  # configured under old storage id
    }

    resolved = await resolve_skill_env_map(backend, env_vars)  # type: ignore[arg-type]

    assert resolved == {"slack_notifier_skill": {"SLACK_TOKEN": "x"}}


@pytest.mark.asyncio
async def test_resolve_keeps_env_when_keyed_by_runtime_name() -> None:
    """Env configured directly under the runtime name stays in place."""
    backend = _FakeSkillBackend([_skill("demo_skill")])
    env_vars: dict[str, dict[str, str]] = {"demo_skill": {"SK": "1"}}

    resolved = await resolve_skill_env_map(backend, env_vars)  # type: ignore[arg-type]

    assert resolved == {"demo_skill": {"SK": "1"}}


@pytest.mark.asyncio
async def test_resolve_drops_env_for_uninstalled_skills() -> None:
    """Env configs for skills no longer installed are pruned."""
    backend = _FakeSkillBackend([_skill("demo_skill")])
    env_vars: dict[str, dict[str, str]] = {
        "demo_skill": {"SK": "1"},
        "removed_skill": {"GHOST": "1"},
    }

    resolved = await resolve_skill_env_map(backend, env_vars)  # type: ignore[arg-type]

    assert resolved == {"demo_skill": {"SK": "1"}}


@pytest.mark.asyncio
async def test_resolve_returns_input_without_backend_or_env() -> None:
    """No backend or empty config short-circuits to the input as-is."""
    env_vars: dict[str, dict[str, str]] = {"demo_skill": {"SK": "1"}}

    assert await resolve_skill_env_map(None, env_vars) == env_vars  # type: ignore[arg-type]
    assert await resolve_skill_env_map(_FakeSkillBackend([]), {}) == {}  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_returns_input_on_backend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend failure falls back to the unvalidated input map."""
    backend = _FakeSkillBackend([])

    async def _boom() -> list[SkillMetadata]:
        raise RuntimeError("storage down")

    monkeypatch.setattr(backend, "list_skills", _boom)
    env_vars: dict[str, dict[str, str]] = {"demo_skill": {"SK": "1"}}

    resolved = await resolve_skill_env_map(backend, env_vars)  # type: ignore[arg-type]

    assert resolved == env_vars
