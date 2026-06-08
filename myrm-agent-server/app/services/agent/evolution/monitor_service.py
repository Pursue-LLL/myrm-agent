"""Skill Evolution Monitor Service

This service wraps the Harness-level MetricMonitor to periodically scan for
high-error-rate skills, trigger deep evaluation, and push the resulting
EvolutionProposals via WebSocket to the frontend.
"""

import asyncio
import logging

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal
from myrm_agent_harness.agent.skills.evolution.infra.integration import (
    EvolutionIntegration,
)
from myrm_agent_harness.agent.skills.evolution.infra.monitor import MetricMonitor

from app.services.skills.ws_hub import broadcast_message, broadcast_proposal

logger = logging.getLogger(__name__)


async def _broadcast_auto_merged_evolution(proposal_dict: dict[str, object]) -> None:
    """Notify WebSocket clients that an evolution was auto-merged (same channel as proposals)."""
    await broadcast_message("AUTO_MERGED_EVOLUTION", proposal_dict)


class SkillEvolutionMonitorService:
    """Business-layer wrapper for background skill evolution scanning."""

    def __init__(self, integration: EvolutionIntegration) -> None:
        self._integration = integration
        self._monitor: MetricMonitor | None = None
        self._task: asyncio.Task[None] | None = None
        self._evidence_task: asyncio.Task[None] | None = None

    async def _on_new_proposal(self, proposal: EvolutionProposal) -> None:
        """Callback invoked by the Harness when a new proposal is generated."""
        logger.info(f"New evolution proposal received for skill: {proposal.skill_id} (Score: {proposal.score})")

        # Persist the proposal through ConfidenceApprovalFlow so it lands on the approval-backed evolution review chain
        try:
            from app.services.agent.confidence_approval_flow import (
                ConfidenceApprovalFlow,
            )

            flow = ConfidenceApprovalFlow()
            result = await flow.process_evolution(proposal)
        except Exception as e:
            logger.error(f"Failed to persist EvolutionProposal for skill {proposal.skill_id}: {e}")
            return

        proposal_dict = proposal.to_dict()

        if result.approved:
            await _broadcast_auto_merged_evolution(proposal_dict)
        else:
            await broadcast_proposal(proposal_dict)

    _EVIDENCE_INTERVAL_SECONDS = 3600  # Run evidence evolution every hour

    async def start(self) -> None:
        """Start the background monitor task."""
        if self._task is not None:
            return

        # Initialize the Harness monitor
        self._monitor = MetricMonitor(
            store=self._integration.store,
            engine=self._integration.engine,
            llm_client=(self._integration.engine._llm if hasattr(self._integration.engine, "_llm") else None),
            scan_interval=5,
            on_evolution_complete=self._on_new_proposal,
        )

        # Start the background loop
        self._task = asyncio.create_task(self._monitor.start())
        self._evidence_task = asyncio.create_task(self._evidence_evolution_loop())
        logger.info("SkillEvolutionMonitorService started (monitor + hourly evidence evolution)")

    async def _evidence_evolution_loop(self) -> None:
        """Periodically run cross-session evidence aggregation evolution."""
        await asyncio.sleep(60)  # Initial delay to let system stabilize
        while True:
            try:
                proposals = await self._integration.run_evidence_evolution(
                    on_proposal_callback=self._on_new_proposal,
                )
                if proposals:
                    logger.info(
                        "Evidence evolution produced %d proposals",
                        len(proposals),
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Evidence evolution loop error: %s", e, exc_info=True)
            await asyncio.sleep(self._EVIDENCE_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop the background monitor task."""
        if self._monitor:
            await self._monitor.stop()
        for task in (self._task, getattr(self, "_evidence_task", None)):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None
        self._evidence_task = None
        logger.info("SkillEvolutionMonitorService stopped")


# Global singleton
_monitor_service: SkillEvolutionMonitorService | None = None


async def init_evolution_monitor_service() -> None:
    """Initialize and start the global evolution monitor service."""
    global _monitor_service
    if _monitor_service is not None:
        return

    from pathlib import Path

    # Initialize EvolutionIntegration if it doesn't exist
    from myrm_agent_harness.agent.skills.evolution.infra.integration import (
        get_global_evolution_integration,
    )
    from myrm_agent_harness.toolkits.llms import llm_manager

    evolution = get_global_evolution_integration()
    service_holder: list[SkillEvolutionMonitorService | None] = [None]

    def _on_proposal_callback(p: EvolutionProposal) -> None:
        svc = service_holder[0]
        if svc is not None:
            asyncio.create_task(svc._on_new_proposal(p))

    if not evolution:
        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            get_embedding_service,
        )

        from app.config.settings import settings as _settings
        from app.core.retriever.vector.defaults import create_default_vector_store
        from app.services.agent.platform_config import (
            load_platform_model_config,
            require_platform_embedding_config,
        )

        db_path = Path(_settings.database.state_dir).expanduser() / "skills.db"

        try:
            platform_model = await load_platform_model_config()
        except Exception as exc:
            logger.warning(
                "SkillEvolutionMonitorService disabled: WebUI default model not configured (%s)",
                exc,
            )
            return

        llm = await llm_manager.get_llm_from_config(platform_model)

        try:
            embedding_cfg = await require_platform_embedding_config()
        except Exception as exc:
            logger.warning(
                "SkillEvolutionMonitorService disabled: WebUI embedding not configured (%s)",
                exc,
            )
            return

        from app.core.channel_bridge.config_loader import load_user_configs

        user_configs = await load_user_configs()
        search_service_cfg = user_configs.search_cfg if user_configs.search_is_user_configured else None

        vector_store = await create_default_vector_store()
        embedding = get_embedding_service(embedding_cfg)

        from myrm_agent_harness.agent.skills.evolution.pipeline.screener import (
            EvolutionScreener,
        )

        screener = EvolutionScreener(store=None, cheap_llm=llm, cooldown_seconds=3600)

        evolution = EvolutionIntegration(
            db_path=db_path,
            llm=llm,
            enable_background_queue=True,
            enable_tde=True,
            enable_tool_calling=True,
            vector_store=vector_store,
            embedding=embedding,
            screener=screener,
            search_service_cfg=search_service_cfg,
        )

        # Fix screener store reference
        evolution.screener._store = evolution.store

        # Sync vector store on startup
        await evolution.store.sync_vectors()

        # Start the background queue to process evolutions
        await evolution.start_background_queue(on_proposal_callback=_on_proposal_callback)

    _monitor_service = SkillEvolutionMonitorService(evolution)
    service_holder[0] = _monitor_service
    await _monitor_service.start()


async def shutdown_evolution_monitor_service() -> None:
    """Stop the global evolution monitor service."""
    global _monitor_service
    if _monitor_service:
        await _monitor_service.stop()
        _monitor_service = None
