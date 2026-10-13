"""Unified market install flow wires replace, audit, mount, and adopt."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.discovery.market_install_flow import (
    run_market_install_flow_by_id,
    run_market_install_flow_from_url,
)


@dataclass(frozen=True)
class _MountStub:
    mounted: bool
    agent_id: str = "agent-1"
    mount_skill_id: str = "prebuilt::demo"


@pytest.mark.asyncio
async def test_flow_by_id_runs_replace_audit_mount_adopt(monkeypatch: pytest.MonkeyPatch) -> None:
    install_result = SkillInstallResult(success=True, skill_id="prebuilt::demo", skill_name="Demo")
    replace = AsyncMock(return_value=(install_result, "batch-1", False))
    ensure = AsyncMock()
    audit = AsyncMock()
    mount = AsyncMock(return_value=_MountStub(mounted=True))
    monkeypatch.setattr(
        "app.core.skills.discovery.replace_install.market_install_with_replace_snapshot",
        replace,
    )
    from app.core.skills.marketplace.market_service import market_service

    monkeypatch.setattr(market_service, "ensure_clawhub_registry", ensure)
    monkeypatch.setattr("app.core.skills.audit.audit_skill_action", audit)
    monkeypatch.setattr("app.core.skills.discovery.market_install_flow.maybe_mount_after_install", mount)
    monkeypatch.setattr(
        "app.ai_agents.general_agent.context.get_current_agent_id",
        lambda: "agent-1",
    )

    flow = await run_market_install_flow_by_id(
        "skill-a",
        "clawhub",
        agent_id="agent-1",
        mount_to_agent=True,
    )

    assert flow.result.success is True
    assert flow.pre_replace_batch_id == "batch-1"
    ensure.assert_awaited_once()
    replace.assert_awaited_once()
    audit.assert_called_once()
    mount.assert_awaited_once()


@pytest.mark.asyncio
async def test_flow_from_url_skips_mount_when_install_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    replace = AsyncMock(return_value=(SkillInstallResult(success=False, error="nope"), None, False))
    mount = AsyncMock()
    monkeypatch.setattr(
        "app.core.skills.discovery.replace_install.market_install_from_url_with_replace_snapshot",
        replace,
    )
    from app.core.skills.marketplace.market_service import market_service

    monkeypatch.setattr(market_service, "ensure_clawhub_registry", AsyncMock())
    monkeypatch.setattr("app.core.skills.discovery.market_install_flow.maybe_mount_after_install", mount)

    flow = await run_market_install_flow_from_url("https://github.com/o/r")

    assert flow.result.success is False
    mount.assert_not_called()


@pytest.mark.asyncio
async def test_flow_from_url_success_runs_audit_and_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    install_result = SkillInstallResult(success=True, skill_id="local::abc", skill_name="FromUrl")
    replace = AsyncMock(return_value=(install_result, "batch-u", True))
    audit = AsyncMock()
    mount = AsyncMock(return_value=_MountStub(mounted=True, mount_skill_id="local::abc"))
    monkeypatch.setattr(
        "app.core.skills.discovery.replace_install.market_install_from_url_with_replace_snapshot",
        replace,
    )
    from app.core.skills.marketplace.market_service import market_service

    monkeypatch.setattr(market_service, "ensure_clawhub_registry", AsyncMock())
    monkeypatch.setattr("app.core.skills.audit.audit_skill_action", audit)
    monkeypatch.setattr("app.core.skills.discovery.market_install_flow.maybe_mount_after_install", mount)

    flow = await run_market_install_flow_from_url("https://github.com/o/r")

    assert flow.snapshot_truncated is True
    assert flow.pre_replace_batch_id == "batch-u"
    audit.assert_called_once()
    mount.assert_awaited_once()


@pytest.mark.asyncio
async def test_flow_skips_mount_when_mount_to_agent_false(monkeypatch: pytest.MonkeyPatch) -> None:
    install_result = SkillInstallResult(success=True, skill_id="prebuilt::x", skill_name="X")
    monkeypatch.setattr(
        "app.core.skills.discovery.replace_install.market_install_with_replace_snapshot",
        AsyncMock(return_value=(install_result, None, False)),
    )
    from app.core.skills.marketplace.market_service import market_service

    monkeypatch.setattr(market_service, "ensure_clawhub_registry", AsyncMock())
    monkeypatch.setattr("app.core.skills.audit.audit_skill_action", lambda *a, **k: None)
    mount = AsyncMock()
    monkeypatch.setattr("app.core.skills.discovery.market_install_flow.maybe_mount_after_install", mount)

    flow = await run_market_install_flow_by_id("id", "clawhub", mount_to_agent=False)

    assert flow.result.success is True
    mount.assert_not_called()


@pytest.mark.asyncio
async def test_flow_resolves_agent_id_from_context_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    install_result = SkillInstallResult(success=True, skill_id="prebuilt::demo", skill_name="Demo")
    monkeypatch.setattr(
        "app.core.skills.discovery.replace_install.market_install_with_replace_snapshot",
        AsyncMock(return_value=(install_result, None, False)),
    )
    from app.core.skills.marketplace.market_service import market_service

    monkeypatch.setattr(market_service, "ensure_clawhub_registry", AsyncMock())
    monkeypatch.setattr("app.core.skills.audit.audit_skill_action", lambda *a, **k: None)
    mount = AsyncMock(return_value=_MountStub(mounted=True, agent_id="ctx-agent"))
    monkeypatch.setattr("app.core.skills.discovery.market_install_flow.maybe_mount_after_install", mount)
    monkeypatch.setattr(
        "app.ai_agents.general_agent.context.get_current_agent_id",
        lambda: "ctx-agent",
    )

    await run_market_install_flow_by_id("skill-a", "clawhub", agent_id=None, mount_to_agent=True)

    mount.assert_awaited_once()
    call_kwargs = mount.await_args.kwargs
    assert call_kwargs["agent_id"] == "ctx-agent"
