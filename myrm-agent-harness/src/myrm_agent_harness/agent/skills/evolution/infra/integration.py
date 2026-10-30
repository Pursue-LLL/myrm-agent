"""Integration helpers for skill evolution system.

Makes it easy for business layer to enable evolution capabilities.
Framework provides the hooks, business layer decides when to use them.

[INPUT]
- agent.skills.evolution.core.types::EvolutionProposal, (POS: Data types for skill evolution system.)
- agent.skills.evolution.core.engine::SkillEvolutionEngine (POS: Skill evolution engine - Core of self-evolution system.)
- agent.skills.evolution.db.store::SkillStore (POS: SQLite persistence for skill evolution system.)
- toolkits.code_execution.executors.test_executor::SubprocessCodeExecutor (POS: Subprocess-based test execution for skill evolution TDE.)
- agent.skills.evolution.pipeline.screener::EvolutionScreener (POS: myrm_agent_harness/agent/skills/evolution/screener.py ## Architecture Two-phase screening to block "snowball effect" of blind fixes: **Phase 1: Rule-based (Cooldown)** Rejects repeated evolution attempts within cooldown period Checks both skill.updated_at and rejection history Zero LLM cost, instant response **Phase 2: LLM Confirmation (Cheap Model)** Only for FIX evolution type Analyzes real error logs (HTTP status, exception stack) Asks cheap LLM: "Is this really a skill code defect?" Returns YES (proceed) or NO + reason (block) **Prometheus Metrics (Observability)** evolution_screening_total: Counter by phase + result evolution_screening_confidence: Histogram of LLM confidence evolution_screening_duration_seconds: Histogram of screening duration by phase ## Design Principles 1. **Cost Optimization**: Use gpt-4o-mini/claude-haiku for Phase 2 2. **Fail-Safe**: LLM errors → Allow (don't block valid fixes) 3. **Transparency**: Record all rejections for audit 4. **Signal Extraction**: Focus on HTTP status + exception type vs full stack 5. **Observability**: Expose Prometheus metrics for monitoring and tuning)
- agent.event_log.protocols::EventLogBackend (POS: Protocol contract. Framework provides FileEventLogBackend; business layer may extend with SQLite / PostgreSQL implementations.)

[OUTPUT]
- EvolutionIntegration: All-in-one integration helper for skill evolution.
- get_global_evolution_integration: Get the global EvolutionIntegration instance if configured.
- set_global_evolution_integration: Set the global EvolutionIntegration instance.
- enable_skill_evolution: Enable skill evolution with one function call.

[POS]
Integration helpers for skill evolution system. Provides EvolutionIntegration singleton with
screening, manual evolution and background queue orchestration.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.agent.skills.evolution.core.engine import SkillEvolutionEngine
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionRequest,
    EvolutionStrategy,
    EvolutionType,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.agent.skills.evolution.execution.dependency import (
    get_dependency_tracker,
)
from myrm_agent_harness.agent.skills.evolution.infra.queue import (
    EvolutionQueue,
    get_evolution_queue,
)
from myrm_agent_harness.agent.skills.evolution.pipeline.screener import (
    EvolutionScreener,
)
from myrm_agent_harness.toolkits.code_execution.executors.test_executor import (
    SubprocessCodeExecutor,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.event_log.protocols import EventLogBackend

logger = logging.getLogger(__name__)

# Receives each proposal a background evolution produces; may be sync or async.
ProposalCallback = Callable[[EvolutionProposal], Awaitable[None] | None]

_global_evolution_integration: "EvolutionIntegration | None" = None


def get_global_evolution_integration() -> "EvolutionIntegration | None":
    """Get the global EvolutionIntegration instance if configured."""
    return _global_evolution_integration


def set_global_evolution_integration(
    integration: "EvolutionIntegration | None",
) -> None:
    """Set the global EvolutionIntegration instance."""
    global _global_evolution_integration
    _global_evolution_integration = integration


class EvolutionIntegration:
    """All-in-one integration helper for skill evolution.

    Framework-layer helper that provides out-of-the-box evolution capabilities.
    Business layer can enable evolution by instantiating this class.

    Example (business layer):
        ```python
        from myrm_agent_harness.agent.skills.evolution import EvolutionIntegration

        # Enable evolution with one line
        evolution = EvolutionIntegration(
            db_path=".myrm/skills_evolution.db",
            llm=your_chat_model)

        # Auto-evolve in background
        await evolution.start_background_queue()
        ```
    """

    def __init__(
        self,
        db_path: Path | str = ".myrm/skills_evolution.db",
        *,
        llm: BaseChatModel | None = None,
        enable_background_queue: bool = False,
        queue_workers: int = 2,
        screener: "EvolutionScreener | None" = None,
        enable_tde: bool = False,
        test_executor: "SubprocessCodeExecutor | None" = None,
        event_log_backend: "EventLogBackend | None" = None,
        evolution_strategy: EvolutionStrategy = "balanced",
    ):
        """Initialize evolution integration.

        Args:
            db_path: Path to SQLite database for skill storage
            llm: LLM client for evolution (BaseChatModel, business layer provides)
            enable_background_queue: Enable background evolution queue
            queue_workers: Number of queue workers (if enabled)
            screener: Optional EvolutionScreener instance for two-phase filtering (injected by business layer)
            enable_tde: Enable test-driven evolution with generated pytest validation (default False)
            test_executor: Optional subprocess test executor (auto-created if enable_tde=True and None)
            event_log_backend: Event log read by the engine to build the FIX failure trajectory
            evolution_strategy: Controls screener behavior: balanced (all types), innovate (all types, and a
                rejection the confirmation check is unsure about is overridden), repair-only (FIX only).
                Business layer injects user preference.
        """
        self.db_path = Path(db_path)

        # Core components
        self.store = SkillStore(self.db_path)
        self.test_executor: SubprocessCodeExecutor | None = test_executor
        self.screener: EvolutionScreener | None = screener
        self._evolution_strategy: EvolutionStrategy = evolution_strategy

        # Propagate strategy to screener if injected
        if self.screener is not None:
            self.screener.evolution_strategy = evolution_strategy

        # Evolution engine (requires LLM client from business layer)
        self.engine: SkillEvolutionEngine | None = None

        if llm:
            if enable_tde and self.test_executor is None:
                self.test_executor = SubprocessCodeExecutor()
                logger.debug("EvolutionIntegration: auto-created subprocess test executor")

            self.engine = SkillEvolutionEngine(
                store=self.store,
                llm=llm,
                event_log_backend=event_log_backend,
            )

        # Optional components
        self.dependency_tracker = get_dependency_tracker()

        self.queue: EvolutionQueue | None = None
        if enable_background_queue:
            self.queue = get_evolution_queue(worker_count=queue_workers)

        logger.info(
            "Evolution integration initialized: db=%s, llm=%s, queue=%s",
            self.db_path,
            llm is not None,
            enable_background_queue,
        )

        # Register as global instance so middlewares can access it
        set_global_evolution_integration(self)

    @property
    def evolution_strategy(self) -> EvolutionStrategy:
        """Current evolution strategy."""
        return self._evolution_strategy

    @evolution_strategy.setter
    def evolution_strategy(self, value: EvolutionStrategy) -> None:
        """Hot-update evolution strategy (propagates to screener)."""
        self._evolution_strategy = value
        if self.screener is not None:
            self.screener.evolution_strategy = value
        logger.info("Evolution strategy updated to '%s'", value)

    async def evolve_skill(
        self,
        skill_id: str,
        evolution_type: EvolutionType,
        *,
        reason: str | None = None,
        user_feedback: str = "",
        force_retry: bool = False,
    ) -> EvolutionProposal | None:
        """Manually trigger skill evolution.

        Args:
            skill_id: Skill to evolve
            evolution_type: Type of evolution
            reason: Failure description for FIX ("Manual fix" when omitted)
            user_feedback: User feedback for DERIVED
            force_retry: Bypass the screener cooldown (explicit GUI retry)

        Returns:
            EvolutionProposal or None if failed
        """
        if not self.engine:
            logger.error("Evolution engine not initialized (no LLM client)")
            return None

        # Apply screener if available
        if self.screener:
            request = EvolutionRequest(
                evolution_type=evolution_type,
                skill_id=skill_id,
                reason=reason or "",
                user_feedback=user_feedback,
                force_retry=force_retry,
            )
            screening_result = await self.screener.screen_request(request)
            if not screening_result.allowed:
                logger.info(
                    "Evolution for skill '%s' blocked by screener: %s",
                    skill_id,
                    screening_result.reason,
                )
                return None

        if evolution_type == EvolutionType.FIX:
            return await self.engine.fix_skill(skill_id, "Manual fix" if reason is None else reason)
        elif evolution_type == EvolutionType.DERIVED:
            return await self.engine.derive_skill_simple(skill_id, user_feedback)

        return None

    async def start_background_queue(self, on_proposal_callback: ProposalCallback | None = None) -> None:
        """Start background evolution queue.

        Args:
            on_proposal_callback: Optional callback to notify GUI/Server when a proposal is ready.
        """
        if not self.queue:
            logger.warning("Background queue not enabled")
            return

        if not self.engine:
            logger.error("Cannot start queue without evolution engine")
            return

        # Set evolution handler
        async def evolution_handler(
            request: EvolutionRequest,
        ) -> EvolutionProposal | None:
            proposal = await self.evolve_skill(
                request.skill_id or "",
                request.evolution_type,
                reason=request.reason,
                user_feedback=request.user_feedback,
                force_retry=request.force_retry,
            )
            if proposal and on_proposal_callback:
                try:
                    outcome = on_proposal_callback(proposal)
                    if inspect.isawaitable(outcome):
                        await outcome
                except Exception as e:
                    logger.error(f"Proposal callback failed: {e}")
            return proposal

        self.queue.set_evolution_handler(evolution_handler)
        await self.queue.start()
        logger.info("Background evolution queue started")

    async def stop_background_queue(self) -> None:
        """Stop background evolution queue."""
        if self.queue:
            await self.queue.stop()

    async def close(self) -> None:
        """Cleanup resources."""
        if self.queue:
            await self.stop_background_queue()

        self.store.close()
        logger.info("Evolution integration closed")


# Convenience function for business layer
def enable_skill_evolution(
    db_path: Path | str = ".myrm/skills_evolution.db",
    *,
    llm: BaseChatModel | None = None,
    enable_background_queue: bool = False,
    queue_workers: int = 2,
    screener: "EvolutionScreener | None" = None,
    event_log_backend: "EventLogBackend | None" = None,
    evolution_strategy: EvolutionStrategy = "balanced",
) -> EvolutionIntegration:
    """Enable skill evolution with one function call.

    Framework-provided convenience function for business layer.

    Args:
        db_path: Path to evolution database
        llm: LLM client for evolution (BaseChatModel)
        enable_background_queue: Enable the background evolution queue
        queue_workers: Number of queue workers (if enabled)
        screener: Optional EvolutionScreener for two-phase filtering
        event_log_backend: Optional backend for trace extraction.
        evolution_strategy: Controls screener behavior (balanced/innovate/repair-only).

    Test-driven evolution is set on ``EvolutionIntegration`` directly.

    Returns:
        EvolutionIntegration instance

    Example:
        ```python
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model="gpt-4")
        evolution = enable_skill_evolution(
            db_path=".myrm/skills.db",
            llm=llm,
            enable_background_queue=True,
            evolution_strategy="repair-only",
            event_log_backend=your_backend,
        )
        ```
    """
    return EvolutionIntegration(
        db_path,
        llm=llm,
        enable_background_queue=enable_background_queue,
        queue_workers=queue_workers,
        screener=screener,
        event_log_backend=event_log_backend,
        evolution_strategy=evolution_strategy,
    )
