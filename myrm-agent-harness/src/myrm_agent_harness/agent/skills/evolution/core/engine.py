"""Skill evolution engine - Core of self-evolution system.

Implements 2 evolution types as a lightweight orchestrator:
- FIX: Auto-repair failed skills via trace analysis
- DERIVED: Optimize based on feedback (with Improvement Gate)

Improvement Gate: the DERIVED path injects the original skill as a baseline
candidate in evaluation. If no variant scores higher than the original,
evolution is skipped to prevent quality regression.

Works from the SKILL.md on disk (the store's copy of its text and its lock can lag behind an edit) and
returns standardized EvolutionProposal objects, delegating application and persistence to the
business layer (Server/GUI).

[INPUT]
- agent.skills.evolution.db.store::SkillStore (POS: SQLite persistence for skill evolution system.)
- agent.skills.evolution.execution.evaluator::BatchEvaluator (POS: Batch Evaluator for Skill Evolution.)
- agent.skills.evolution.pipeline.trace_analyzer::TraceAnalyzer (POS: Trace Analyzer for Skill Evolution.)
- agent.skills.evolution.pipeline.variant_generator::VariantGenerator (POS: Variant Generator for Skill Evolution.)
- agent.event_log.protocol::EventLogBackend (POS: Protocol contract. Framework provides FileEventLogBackend; business layer may extend with SQLite / PostgreSQL implementations.)
- agent.skills.evolution.safety.validator::SkillValidator (POS: Skill evolution validation system.)
- agent.skills.evolution.execution.sandbox_validator::SandboxValidator (POS: Sandbox validation for evolved skills.)
- agent.skills.evolution.core.eval_regression::filter_variants_by_regression (POS: Non-blocking regression gate for the skill evolution pipeline.)
- agent.skills.evolution.core.skill_on_disk::skill_from_disk (POS: The SKILL.md of a skill as it is on disk, the text and the evolution lock the evolution engine works from.)

[OUTPUT]
- SkillEvolutionEngine: Core orchestrator for skill self-evolution.

[POS]
Skill evolution engine - Core of self-evolution system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.agent.skills.evolution.core.proposal_builder import (
    ProposalBuilder,
)
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.agent.skills.evolution.execution.evaluator import BatchEvaluator
from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import (
    TraceAnalyzer,
)
from myrm_agent_harness.agent.skills.evolution.pipeline.variant_generator import (
    VariantGenerator,
)

from .eval_regression import filter_variants_by_regression
from .skill_on_disk import skill_from_disk

if TYPE_CHECKING:
    from myrm_agent_harness.agent.event_log.protocols import EventLogBackend

logger = logging.getLogger(__name__)

__all__ = ["SkillEvolutionEngine"]


class SkillEvolutionEngine:
    """Core orchestrator for skill self-evolution.

    Framework layer component:
    - Analyzes full execution traces (TraceAnalyzer)
    - Generates multiple variants (VariantGenerator)
    - Evaluates variants via LLM-as-judge (BatchEvaluator)
    - Outputs standardized EvolutionProposal
    """

    def __init__(
        self,
        store: SkillStore,
        llm: BaseChatModel | None = None,
        event_log_backend: EventLogBackend | None = None,
        num_variants_per_evolution: int = 3,
    ):
        """Initialize the lightweight evolution engine.

        Args:
            store: SkillStore for persistence (read-only in engine).
            llm: LLM client for generating evolved skills.
            event_log_backend: Optional backend for trace extraction.
            num_variants_per_evolution: Number of variants to generate per run.
        """
        self._store = store
        self._llm = llm
        self._num_variants = num_variants_per_evolution

        # Initialize sub-modules
        self._trace_analyzer = TraceAnalyzer(event_log_backend) if event_log_backend else None
        self._variant_generator = VariantGenerator(llm)
        self._evaluator = BatchEvaluator(llm)
        self._proposal_builder = ProposalBuilder()

    async def fix_skill(
        self,
        skill_id: str,
        error_message: str,
        task_context: str | None = None,
        session_id: str | None = None,
    ) -> EvolutionProposal | None:
        """FIX evolution: Propose repair for a failed skill.

        The repair is always generated from the failure trajectory: variants
        are produced and judged by the LLM, filtered by the EvalCase regression
        gate, and returned as a proposal for the failing skill itself.
        """
        old_skill = self._store.get_skill(skill_id)
        if not old_skill:
            logger.error(f"FIX evolution: skill not found: {skill_id}")
            return None

        old_skill = skill_from_disk(old_skill)
        if old_skill.evolution_locked:
            logger.warning(f"FIX skipped: skill '{old_skill.name}' is locked.")
            return None

        logger.info(f"FIX evolution started for '{old_skill.name}'")

        # 1. Extract Trajectory
        trajectory = ""
        if self._trace_analyzer and session_id:
            trajectory = await self._trace_analyzer.extract_trajectory(session_id, old_skill.skill_id)
        if not trajectory:
            trajectory = f"Trajectory extraction not available. Error: {error_message}"

        # 1.5 The reasons the user gave when rejecting earlier proposals for this skill
        constraints = self._store.get_evolution_constraints(skill_id, limit=5)
        formatted_constraints = "\n".join([f"- {c}" for c in constraints]) if constraints else ""

        # 2. Generate Variants
        feedback = f"Error: {error_message}\nContext: {task_context or 'None'}"
        variants = await self._variant_generator.generate_variants(
            skill=old_skill,
            feedback=feedback,
            trajectory=trajectory,
            num_variants=self._num_variants,
            constraints=formatted_constraints,
        )

        if not variants:
            return None

        # 2.5. EvalCase Regression Gate (non-blocking score penalty)
        variants, regression_penalties = await filter_variants_by_regression(
            old_skill,
            variants,
            logger,
        )
        if not variants:
            logger.warning("All variants failed EvalCase regression for '%s'", old_skill.name)
            return None

        # 3. Evaluate Variants
        best_variant, score, reason, is_general = await self._evaluator.evaluate_variants(
            original_skill=old_skill,
            variants=variants,
            feedback=feedback,
            trajectory=trajectory,
        )

        # Apply regression penalty to final score (non-blocking)
        penalty = regression_penalties.get(best_variant, 0.0)
        if penalty > 0:
            score = max(0.0, score - penalty)
            reason = f"[Regression penalty: -{penalty:.2f}] {reason}"

        # 4. Build Proposal
        proposal = self._proposal_builder.build_proposal(
            skill=old_skill,
            evolution_type=EvolutionType.FIX,
            best_variant=best_variant,
            score=score,
            reasoning=reason,
            task_context=task_context or "",
            trajectory=trajectory,
            is_general=is_general,
        )

        return proposal

    async def derive_skill_simple(self, skill_id: str, user_feedback: str) -> EvolutionProposal | None:
        """DERIVED evolution: Optimize skill based on feedback."""
        old_skill = self._store.get_skill(skill_id)
        if not old_skill:
            logger.error(f"DERIVED evolution: skill not found: {skill_id}")
            return None

        old_skill = skill_from_disk(old_skill)
        if old_skill.evolution_locked:
            logger.warning(f"DERIVED skipped: '{old_skill.name}' is locked.")
            return None

        logger.info(f"DERIVED evolution started for '{old_skill.name}'")

        trajectory = "User initiated optimization."
        constraints = self._store.get_evolution_constraints(skill_id, limit=5)
        formatted_constraints = "\n".join([f"- {c}" for c in constraints]) if constraints else ""

        variants = await self._variant_generator.generate_variants(
            skill=old_skill,
            feedback=user_feedback,
            trajectory=trajectory,
            num_variants=self._num_variants,
            constraints=formatted_constraints,
        )

        if not variants:
            return None

        # EvalCase Regression Gate (non-blocking score penalty)
        variants, regression_penalties = await filter_variants_by_regression(
            old_skill,
            variants,
            logger,
        )
        if not variants:
            logger.warning("All variants failed EvalCase regression for '%s'", old_skill.name)
            return None

        # Improvement Gate: inject original as baseline to prevent quality regression
        variants_with_baseline = [old_skill.content, *variants]

        best_variant, score, reason, is_general = await self._evaluator.evaluate_variants(
            original_skill=old_skill,
            variants=variants_with_baseline,
            feedback=user_feedback,
            trajectory=trajectory,
        )

        if best_variant == old_skill.content:
            logger.info("DERIVED improvement gate: original skill won evaluation for '%s'", old_skill.name)
            return None

        penalty = regression_penalties.get(best_variant, 0.0)
        if penalty > 0:
            score = max(0.0, score - penalty)
            reason = f"[Regression penalty: -{penalty:.2f}] {reason}"

        proposal = self._proposal_builder.build_proposal(
            skill=old_skill,
            evolution_type=EvolutionType.DERIVED,
            best_variant=best_variant,
            score=score,
            reasoning=reason,
            task_context=user_feedback,
            trajectory=trajectory,
            is_general=is_general,
        )

        return proposal
