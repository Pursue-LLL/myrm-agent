"""Chat agent market install post-hooks mirror Discover API."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.discovery.agent_market_install import (
    AgentSessionSkillMarketBackend,
    apply_agent_session_post_install,
    make_agent_session_install_from_url_fn,
)


@dataclass(frozen=True)
class _MountStub:
    mounted: bool
    agent_id: str = "agent-1"
    mount_skill_id: str = "prebuilt::demo"


@pytest.mark.asyncio
async def test_apply_agent_session_post_install_mounts_and_adopts(monkeypatch: pytest.MonkeyPatch) -> None:
    mount = AsyncMock(return_value=_MountStub(mounted=True))
    adopt = AsyncMock()
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.maybe_mount_after_install",
        mount,
    )
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.complete_discovery_adoption",
        adopt,
    )
    monkeypatch.setattr(
        "app.ai_agents.general_agent.context.get_current_agent_id",
        lambda: "agent-1",
    )

    result = SkillInstallResult(success=True, skill_id="prebuilt::demo", skill_name="Demo")
    await apply_agent_session_post_install(result)

    mount.assert_awaited_once()
    assert mount.await_args.kwargs["mount_to_agent"] is True
    assert mount.await_args.kwargs["agent_id"] == "agent-1"
    adopt.assert_awaited_once_with("agent-1", "prebuilt::demo")


@pytest.mark.asyncio
async def test_apply_agent_session_post_install_skips_on_failed_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mount = AsyncMock()
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.maybe_mount_after_install",
        mount,
    )

    await apply_agent_session_post_install(SkillInstallResult(success=False, error="nope"))
    mount.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrapped_backend_install_ensures_clawhub_registry_before_install() -> None:
    ensure = AsyncMock()
    inner = SimpleNamespace(
        install=AsyncMock(
            return_value=SkillInstallResult(success=True, skill_id="x", skill_name="X"),
        ),
        ensure_clawhub_registry=ensure,
    )
    backend = AgentSessionSkillMarketBackend(inner)

    await backend.install("skill-a", "clawhub")

    ensure.assert_awaited_once()
    inner.install.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrapped_backend_install_runs_post_install(monkeypatch: pytest.MonkeyPatch) -> None:
    post = AsyncMock()
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.apply_agent_session_post_install",
        post,
    )
    inner = SimpleNamespace(
        install=AsyncMock(
            return_value=SkillInstallResult(success=True, skill_id="x", skill_name="X"),
        ),
    )
    backend = AgentSessionSkillMarketBackend(inner)

    out = await backend.install("skill-a", "clawhub", user_id="u1")

    assert out.success is True
    inner.install.assert_awaited_once_with("skill-a", "clawhub")
    post.assert_awaited_once()


@pytest.mark.asyncio
async def test_install_from_url_fn_runs_post_install(monkeypatch: pytest.MonkeyPatch) -> None:
    post = AsyncMock()
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.apply_agent_session_post_install",
        post,
    )
    inner = SimpleNamespace(
        install_from_url=AsyncMock(
            return_value=SkillInstallResult(success=True, skill_id="y", skill_name="Y"),
        ),
    )
    install_url = make_agent_session_install_from_url_fn(inner)

    await install_url("https://github.com/o/r", None)

    inner.install_from_url.assert_awaited_once_with("https://github.com/o/r")
    post.assert_awaited_once()
