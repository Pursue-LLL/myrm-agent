"""Chat agent market install adapter delegates to market_install_flow."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.discovery.agent_market_install import (
    AgentSessionSkillMarketBackend,
    make_agent_session_install_from_url_fn,
)
from app.core.skills.discovery.market_install_flow import MarketInstallFlowResult


@dataclass(frozen=True)
class _MountStub:
    mounted: bool
    agent_id: str = "agent-1"
    mount_skill_id: str = "prebuilt::demo"


def _flow_result() -> MarketInstallFlowResult:
    return MarketInstallFlowResult(
        result=SkillInstallResult(success=True, skill_id="prebuilt::demo", skill_name="Demo"),
        mount_result=_MountStub(mounted=True),
    )


@pytest.mark.asyncio
async def test_wrapped_backend_install_delegates_to_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    flow_fn = AsyncMock(return_value=_flow_result())
    adopt = AsyncMock()
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.run_market_install_flow_by_id",
        flow_fn,
    )
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.complete_discovery_adoption",
        adopt,
    )
    backend = AgentSessionSkillMarketBackend(SimpleNamespace())

    out = await backend.install("skill-a", "clawhub", user_id="u1")

    assert out.skill_id == "prebuilt::demo"
    flow_fn.assert_awaited_once_with(
        "skill-a",
        "clawhub",
        agent_id=None,
        mount_to_agent=True,
    )
    adopt.assert_awaited_once_with("agent-1", "prebuilt::demo")


@pytest.mark.asyncio
async def test_install_from_url_fn_delegates_to_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    flow_fn = AsyncMock(return_value=_flow_result())
    monkeypatch.setattr(
        "app.core.skills.discovery.agent_market_install.run_market_install_flow_from_url",
        flow_fn,
    )
    install_url = make_agent_session_install_from_url_fn(object())

    await install_url("https://github.com/o/r", None)

    flow_fn.assert_awaited_once_with(
        "https://github.com/o/r",
        agent_id=None,
        mount_to_agent=True,
    )
