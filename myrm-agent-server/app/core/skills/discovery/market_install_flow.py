"""Unified external market install pipeline (Discover HTTP and chat skill_market_tool).

[INPUT]
- app.core.skills.marketplace.market_service::market_service (POS: Quarantine install)
- app.core.skills.discovery.replace_install::market_install_with_replace_snapshot (POS: Pre-replace batch)
- app.core.skills.audit::audit_skill_action (POS: Structured install audit log)
- app.core.skills.discovery.mount::maybe_mount_after_install (POS: Catalog enable)

[OUTPUT]
- MarketInstallFlowResult: Install result plus replace batch and mount metadata
- run_market_install_flow_by_id / run_market_install_flow_from_url

[POS]
Single server-side contract for market install: registry, replace snapshot, audit, catalog mount.
Explicit allowlist append runs in Discover HTTP response builder or chat adapter.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.discovery.mount import SkillMountResult, maybe_mount_after_install


@dataclass(frozen=True)
class MarketInstallFlowResult:
    result: SkillInstallResult
    pre_replace_batch_id: str | None = None
    snapshot_truncated: bool = False
    mount_result: SkillMountResult | None = None


async def _resolve_flow_agent_id(agent_id: str | None) -> str | None:
    if agent_id is not None and agent_id.strip():
        return agent_id.strip()
    from app.ai_agents.general_agent.context import get_current_agent_id

    return get_current_agent_id()


async def _mount_after_install(
    result: SkillInstallResult,
    *,
    agent_id: str | None,
    mount_to_agent: bool,
) -> SkillMountResult | None:
    if not result.success or not mount_to_agent:
        return None

    return await maybe_mount_after_install(
        result,
        agent_id=await _resolve_flow_agent_id(agent_id),
        mount_to_agent=True,
    )


async def run_market_install_flow_by_id(
    skill_id: str,
    source: str,
    *,
    allow_downgrade: bool = False,
    batch_kind: str = "market-replace",
    agent_id: str | None = None,
    mount_to_agent: bool = True,
    audit_action: str = "install",
    audit_skill_id_fallback: str = "",
    audit_source: str = "",
) -> MarketInstallFlowResult:
    from app.core.skills.discovery.replace_install import market_install_with_replace_snapshot
    from app.core.skills.marketplace.market_service import market_service

    await market_service.ensure_clawhub_registry()
    result, pre_replace_batch_id, snapshot_truncated = await market_install_with_replace_snapshot(
        skill_id,
        source,
        allow_downgrade=allow_downgrade,
        batch_kind=batch_kind,
    )
    mount_result = None
    if result.success:
        from app.core.skills.audit import audit_skill_action

        audit_skill_action(
            audit_action,
            result.skill_id or audit_skill_id_fallback or skill_id,
            source=audit_source or source,
        )
        mount_result = await _mount_after_install(
            result,
            agent_id=agent_id,
            mount_to_agent=mount_to_agent,
        )
    return MarketInstallFlowResult(
        result=result,
        pre_replace_batch_id=pre_replace_batch_id,
        snapshot_truncated=snapshot_truncated,
        mount_result=mount_result,
    )


async def run_market_install_flow_from_url(
    url: str,
    *,
    allow_downgrade: bool = False,
    batch_kind: str = "market-replace",
    agent_id: str | None = None,
    mount_to_agent: bool = True,
    audit_action: str = "install_from_url",
    audit_source: str = "github",
) -> MarketInstallFlowResult:
    from app.core.skills.discovery.replace_install import market_install_from_url_with_replace_snapshot
    from app.core.skills.marketplace.market_service import market_service

    await market_service.ensure_clawhub_registry()
    result, pre_replace_batch_id, snapshot_truncated = await market_install_from_url_with_replace_snapshot(
        url,
        allow_downgrade=allow_downgrade,
        batch_kind=batch_kind,
    )
    mount_result = None
    if result.success:
        from app.core.skills.audit import audit_skill_action

        audit_skill_action(
            audit_action,
            result.skill_id or url,
            source=audit_source,
        )
        mount_result = await _mount_after_install(
            result,
            agent_id=agent_id,
            mount_to_agent=mount_to_agent,
        )
    return MarketInstallFlowResult(
        result=result,
        pre_replace_batch_id=pre_replace_batch_id,
        snapshot_truncated=snapshot_truncated,
        mount_result=mount_result,
    )
