"""
[INPUT]
- myrm_agent_harness.agent.skills.evolution.infra.integration::EvolutionIntegration (POS: Integration helpers for skill evolution system. Provides EvolutionIntegration singleton with 15-Call Sliding Window trigger, execution ledger recording, and background queue orchestration.)
- app.services.agent.confidence_approval_flow::ConfidenceApprovalFlow (POS: 基于置信度+客观风控信号的智能审批流。高分且低风险静默自动合并，任何风控红灯即降级人工 Diff Review。)
- app.services.skills.ws_hub::broadcast_message, broadcast_proposal (POS: 技能 WebSocket 广播中心。)
[OUTPUT]
- handle_new_proposal: 将后台进化队列产出的提案交给审批流落地，并按结果向前端推送。
- init_evolution_runtime: 启动期构建全局 EvolutionIntegration（进化模型、筛选器、后台队列）。
- shutdown_evolution_runtime: 停止本模块启动的后台进化队列。
[POS]
技能进化运行时装配。只负责把 Harness 的后台进化队列接到业务审批流与 WebSocket，不做任何失败率扫描或自动修复判定。
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal
from myrm_agent_harness.agent.skills.evolution.infra.integration import (
    EvolutionIntegration,
    get_global_evolution_integration,
)
from myrm_agent_harness.agent.skills.evolution.pipeline.screener import EvolutionScreener
from myrm_agent_harness.toolkits.llms import llm_manager

from app.config.settings import settings
from app.core.channel_bridge.config_loader import load_user_configs
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
from app.services.agent.platform_config import load_platform_evolution_model_config
from app.services.skills.ws_hub import broadcast_message, broadcast_proposal

logger = logging.getLogger(__name__)

_started_integration: EvolutionIntegration | None = None


async def handle_new_proposal(proposal: EvolutionProposal) -> None:
    """Persist a queue-produced proposal through the approval flow and notify clients."""
    logger.info("New evolution proposal received for skill: %s (Score: %s)", proposal.skill_id, proposal.score)

    try:
        result = await ConfidenceApprovalFlow().process_evolution(proposal)
    except Exception as e:
        logger.error("Failed to persist EvolutionProposal for skill %s: %s", proposal.skill_id, e)
        return

    proposal_dict = proposal.to_dict()
    if result.approved:
        await broadcast_message("AUTO_MERGED_EVOLUTION", proposal_dict)
    else:
        await broadcast_proposal(proposal_dict)


async def init_evolution_runtime() -> None:
    """Build the global evolution integration and start its background queue."""
    global _started_integration
    if _started_integration is not None or get_global_evolution_integration() is not None:
        return

    try:
        evolution_model = await load_platform_evolution_model_config()
    except Exception as exc:
        logger.warning("Skill evolution runtime disabled: WebUI evolution model not configured (%s)", exc)
        return

    llm = await llm_manager.get_llm_from_config(evolution_model)
    user_configs = await load_user_configs()
    search_service_cfg = user_configs.search_cfg if user_configs.search_is_user_configured else None

    evolution = EvolutionIntegration(
        db_path=Path(settings.database.state_dir).expanduser() / "skills.db",
        llm=llm,
        enable_background_queue=True,
        enable_tde=True,
        enable_tool_calling=True,
        search_service_cfg=search_service_cfg,
    )
    # The screener reads skill history from the integration's own store.
    evolution.screener = EvolutionScreener(
        store=evolution.store,
        cheap_llm=llm,
        cooldown_seconds=3600,
        evolution_strategy=evolution.evolution_strategy,
    )

    await evolution.start_background_queue(on_proposal_callback=handle_new_proposal)
    _started_integration = evolution
    logger.info("Skill evolution runtime started")


async def shutdown_evolution_runtime() -> None:
    """Stop the background evolution queue started by this module."""
    global _started_integration
    if _started_integration is None:
        return
    await _started_integration.stop_background_queue()
    _started_integration = None
    logger.info("Skill evolution runtime stopped")
