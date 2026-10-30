"""Evolution screener - Two-phase filtering to prevent blind evolution.

[INPUT]
- agent.skills.evolution.core.types::EvolutionRequest (POS: Data types for skill evolution system.)
- agent.skills.evolution.core.skill_on_disk::skill_from_disk (POS: The SKILL.md of a skill as it is on disk, the text and the evolution lock the evolution engine works from.)
- agent.skills.evolution.pipeline.confirmation::extract_error_signals, build_confirmation_prompt, parse_confirmation_response (POS: Phase 2 helpers of the evolution screener: the signals of a failure log, the confirmation prompt, the answer.)
- utils.chat_utils::extract_answer_text (POS: LLM 响应答案提取 — 兼容 reasoning 模型 content 空回退)

[OUTPUT]
- EvolutionScreener: Two-phase evolution screener.
- ScreeningResult: Result of evolution screening.

[POS]
Evolution screening pipeline. Implements multi-phase checks including static error interception, GUI-First force retry, and LLM confirmation.

## Architecture

Two-phase screening to block "snowball effect" of blind fixes:

**Phase 0: Evolution lock**
- The store's flag rejects first, without reading the skill; the SKILL.md frontmatter lock rejects next
  (the file is what the user edits, the store's flag can lag behind it)
- A forced retry skips only the cooldown, never the lock

**Phase 1: Rule-based (Cooldown)**
- Rejects repeated evolution attempts within cooldown period
- Checks both skill.updated_at and rejection history
- Zero LLM cost, instant response

**Phase 2: LLM Confirmation (Cheap Model)**
- Only for FIX evolution type
- Judges the skill text of the SKILL.md on disk, not the store's copy
- Analyzes real error logs (HTTP status, exception stack)
- Asks cheap LLM: "Is this really a skill code defect?"
- Returns YES (proceed) or NO + reason (block)

**Prometheus Metrics (Observability)**
- evolution_screening_total: Counter by phase + result
- evolution_screening_confidence: Histogram of LLM confidence
- evolution_screening_duration_seconds: Histogram of screening duration by phase

## Design Principles

1. **Cost Optimization**: Use gpt-4o-mini/claude-haiku for Phase 2
2. **Fail-Safe**: LLM errors → Allow (don't block valid fixes)
3. **Transparency**: Record all rejections for audit
4. **Signal Extraction**: Focus on HTTP status + exception type vs full stack
5. **Observability**: Expose Prometheus metrics for monitoring and tuning
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.skills.evolution.core.skill_on_disk import skill_from_disk
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionRequest,
    EvolutionStrategy,
    EvolutionType,
)
from myrm_agent_harness.agent.skills.evolution.pipeline.confirmation import (
    build_confirmation_prompt,
    extract_error_signals,
    parse_confirmation_response,
)
from myrm_agent_harness.utils.chat_utils import extract_answer_text

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from myrm_agent_harness.agent.event_log import EventLogger
    from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

from myrm_agent_harness.observability.metrics import (
    get_or_create_counter,
    get_or_create_histogram,
)

logger = logging.getLogger(__name__)


SCREENING_TOTAL = get_or_create_counter(
    "evolution_screening_total",
    "Total evolution screening requests",
    (
        "phase",
        "result",
    ),  # phase: cooldown|llm_confirmation|none; result: allowed|blocked
)

SCREENING_CONFIDENCE = get_or_create_histogram(
    "evolution_screening_confidence",
    "LLM confidence distribution for screening decisions",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

SCREENING_DURATION = get_or_create_histogram(
    "evolution_screening_duration_seconds",
    "Evolution screening duration in seconds",
    labelnames=("phase",),  # phase: cooldown|llm_confirmation|total
)

__all__ = ["EvolutionScreener", "ScreeningResult"]


@dataclass
class ScreeningResult:
    """Result of evolution screening."""

    allowed: bool
    reason: str
    phase: str  # "cooldown", "llm_confirmation", "none"
    confidence: float = 0.5  # LLM confidence in decision (0.0-1.0)


class EvolutionScreener:
    """Two-phase evolution screener.

    Phase 1: Rule-based screening (cooldown).
    Phase 2: LLM confirmation (cheap model).

    Benefits:
    - Block 70-80% blind fixes (estimated based on OpenSpace data)
    - Reduce evolution cost by 60-70% (1 cheap LLM call << 1 expensive evolution)
    - Prevent "snowball effect" (fix correct code → new errors → infinite loop)
    """

    # Strategy → allowed evolution types. "balanced" (default) and "innovate" allow every type; "innovate"
    # additionally overrides low-confidence LLM rejections. "repair-only" allows FIX only.
    _STRATEGY_ALLOWED_TYPES: ClassVar[dict[EvolutionStrategy, frozenset[EvolutionType]]] = {
        "balanced": frozenset(EvolutionType),
        "innovate": frozenset(EvolutionType),
        "repair-only": frozenset({EvolutionType.FIX}),
    }

    def __init__(
        self,
        store: SkillStore,
        cheap_llm: BaseChatModel | None = None,
        cooldown_seconds: int = 3600,
        event_logger: EventLogger | None = None,
        evolution_strategy: EvolutionStrategy = "balanced",
    ):
        """Initialize screener.

        Args:
            store: SkillStore for checking history
            cheap_llm: Cheap LLM for Phase 2 (e.g., gpt-4o-mini, claude-haiku-3)
            cooldown_seconds: Cooldown period in seconds (default 1 hour)
            event_logger: Optional EventLogger to record EVOLUTION_REJECTED events
            evolution_strategy: Controls which evolution types are allowed.
                balanced (default) — all types; innovate — all types, and a rejection the
                confirmation check is unsure about is overridden; repair-only — FIX only.
        """
        self._store = store
        self._cheap_llm = cheap_llm
        self._cooldown_seconds = cooldown_seconds
        self._event_logger = event_logger
        self._evolution_strategy: EvolutionStrategy = evolution_strategy

    @property
    def evolution_strategy(self) -> EvolutionStrategy:
        """Current evolution strategy."""
        return self._evolution_strategy

    @evolution_strategy.setter
    def evolution_strategy(self, value: EvolutionStrategy) -> None:
        """Update strategy at runtime (hot-update without restart)."""
        if value not in self._STRATEGY_ALLOWED_TYPES:
            logger.warning("Unknown evolution strategy '%s', falling back to 'balanced'", value)
            value = "balanced"
        self._evolution_strategy = value

    async def screen_request(self, request: EvolutionRequest) -> ScreeningResult:
        """Screen evolution request.

        Args:
            request: Evolution request

        Returns:
            ScreeningResult indicating if request is allowed
        """
        start_time = time.time()

        if not request.skill_id:
            result = ScreeningResult(
                allowed=True,
                reason="No skill ID provided",
                phase="none",
                confidence=1.0,
            )
            SCREENING_TOTAL.labels(phase="none", result="allowed").inc()
            SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
            return result

        # Phase -1: Strategy-based type filtering (zero-cost, before any I/O)
        allowed_types = self._STRATEGY_ALLOWED_TYPES.get(self._evolution_strategy, frozenset(EvolutionType))
        if request.evolution_type not in allowed_types:
            reason = (
                f"Evolution type '{request.evolution_type}' blocked by "
                f"strategy '{self._evolution_strategy}' "
                f"(allowed: {', '.join(sorted(t.value for t in allowed_types))})"
            )
            await self._log_rejection_event(request.skill_id, "strategy", reason)
            SCREENING_TOTAL.labels(phase="strategy", result="blocked").inc()
            SCREENING_DURATION.labels(phase="strategy").observe(time.time() - start_time)
            SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
            SCREENING_CONFIDENCE.observe(1.0)
            return ScreeningResult(allowed=False, reason=reason, phase="strategy", confidence=1.0)

        # Phase 0: Evolution lock check (highest priority, zero-cost)
        if self._store.is_evolution_locked(request.skill_id):
            return await self._reject_locked(
                request.skill_id, "Skill is locked from auto-evolution (user-protected in DB)", start_time
            )

        # Phase 0.5: Intent-Aware Cooldown Override
        # If user explicitly requests to continue fixing via GUI flag, bypass cooldown
        intent_override = request.force_retry
        if intent_override:
            logger.info(
                "Intent-aware cooldown override triggered by GUI force_retry flag for skill '%s'",
                request.skill_id,
            )

        skill = self._store.get_skill(request.skill_id)
        if skill:
            # The lock the user wrote into SKILL.md (the store's flag can lag behind the file)
            skill = skill_from_disk(skill)
            if skill.evolution_locked:
                return await self._reject_locked(
                    request.skill_id, "Skill is locked from auto-evolution (user-protected in SKILL.md)", start_time
                )

            # Phase 1: Cooldown check
            if not intent_override:
                # Check if recently evolved
                now = datetime.now()
                # Ensure both are naive or aware
                updated_at = skill.updated_at
                if updated_at.tzinfo:
                    now = datetime.now(updated_at.tzinfo)

                time_since_evolution = (now - updated_at).total_seconds()
                if time_since_evolution < self._cooldown_seconds:
                    reason = f"Skill recently evolved ({time_since_evolution:.0f}s < {self._cooldown_seconds}s)"
                    await self._log_rejection_event(request.skill_id, "cooldown", reason)
                    # Metrics
                    SCREENING_TOTAL.labels(phase="cooldown", result="blocked").inc()
                    SCREENING_DURATION.labels(phase="cooldown").observe(time.time() - start_time)
                    SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
                    SCREENING_CONFIDENCE.observe(1.0)
                    return ScreeningResult(allowed=False, reason=reason, phase="cooldown", confidence=1.0)

                # Check if recently rejected
                rejections = self._store.load_rejections(skill_id=request.skill_id, limit=1)
                if rejections:
                    last_rejection = rejections[0]
                    try:
                        rejected_at = datetime.fromisoformat(str(last_rejection["rejected_at"]))
                        if rejected_at.tzinfo:
                            now_rej = datetime.now(rejected_at.tzinfo)
                        else:
                            now_rej = datetime.now()
                        time_since_rejection = (now_rej - rejected_at).total_seconds()
                        if time_since_rejection < self._cooldown_seconds:
                            reason = (
                                f"Skill recently rejected ({time_since_rejection:.0f}s < {self._cooldown_seconds}s)"
                            )
                            await self._log_rejection_event(request.skill_id, "cooldown", reason)
                            # Metrics
                            SCREENING_TOTAL.labels(phase="cooldown", result="blocked").inc()
                            SCREENING_DURATION.labels(phase="cooldown").observe(time.time() - start_time)
                            SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
                            SCREENING_CONFIDENCE.observe(1.0)
                            return ScreeningResult(
                                allowed=False,
                                reason=reason,
                                phase="cooldown",
                                confidence=1.0,
                            )
                    except (ValueError, TypeError):
                        pass

        # Phase 1.5: Static Error Type Interception (Bypass LLM for basic syntax errors)
        if request.evolution_type == EvolutionType.FIX and skill:
            error_signals = extract_error_signals(request.reason)
            exception_types = error_signals.get("exception_types", "")

            # If it's a clear syntax or import error, bypass LLM confirmation
            static_bypass_errors = [
                "SyntaxError",
                "IndentationError",
                "NameError",
                "ModuleNotFoundError",
                "ImportError",
                "AttributeError",
                "TypeError",
            ]
            if any(err in exception_types for err in static_bypass_errors):
                reason = f"Static interception: Clear code defect detected ({exception_types})"
                logger.info(
                    "Static interception allowed evolution for skill '%s': %s",
                    skill.name,
                    reason,
                )
                SCREENING_TOTAL.labels(phase="static_interception", result="allowed").inc()
                SCREENING_DURATION.labels(phase="static_interception").observe(time.time() - start_time)
                SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
                SCREENING_CONFIDENCE.observe(1.0)
                return ScreeningResult(
                    allowed=True,
                    reason=reason,
                    phase="static_interception",
                    confidence=1.0,
                )

        # Phase 2: LLM Confirmation (only for FIX evolution)
        if self._cheap_llm and request.evolution_type == EvolutionType.FIX and skill:
            # Extract error signals (HTTP status, exception type)
            error_signals = extract_error_signals(request.reason)

            # Build confirmation prompt
            prompt = build_confirmation_prompt(
                skill_content=skill.content,
                error_log=request.reason,
                error_signals=error_signals,
            )

            try:
                response = await self._cheap_llm.ainvoke([HumanMessage(content=prompt)])
                # 兼容 Anthropic 块列表 / reasoning 模型 content 空回退
                content = extract_answer_text(response).strip()

                # Parse LLM response (supports multiple formats)
                decision, reason, confidence = parse_confirmation_response(content)

                if decision:
                    # LLM confirmed: proceed with evolution
                    logger.info(
                        "LLM confirmed evolution for skill '%s' (confidence=%.2f): %s",
                        skill.name,
                        confidence,
                        reason[:100],
                    )
                    # Metrics
                    SCREENING_TOTAL.labels(phase="llm_confirmation", result="allowed").inc()
                    SCREENING_DURATION.labels(phase="llm_confirmation").observe(time.time() - start_time)
                    SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
                    SCREENING_CONFIDENCE.observe(confidence)
                    return ScreeningResult(
                        allowed=True,
                        reason=reason,
                        phase="llm_confirmation",
                        confidence=confidence,
                    )
                else:
                    # "innovate" strategy: override low-confidence rejections
                    if self._evolution_strategy == "innovate" and confidence < 0.7:
                        logger.info(
                            "Innovate strategy override: allowing evolution for '%s' "
                            "(LLM rejected with low confidence=%.2f)",
                            skill.name,
                            confidence,
                        )
                        SCREENING_TOTAL.labels(phase="llm_confirmation", result="allowed").inc()
                        SCREENING_DURATION.labels(phase="llm_confirmation").observe(time.time() - start_time)
                        SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
                        SCREENING_CONFIDENCE.observe(confidence)
                        return ScreeningResult(
                            allowed=True,
                            reason=f"Innovate override (conf={confidence:.2f}): {reason}",
                            phase="llm_confirmation",
                            confidence=confidence,
                        )

                    # LLM rejected: block evolution
                    logger.info(
                        "LLM rejected evolution for skill '%s' (confidence=%.2f): %s",
                        skill.name,
                        confidence,
                        reason[:100],
                    )
                    await self._log_rejection_event(skill.skill_id, "llm_confirmation", reason, confidence)

                    # Metrics
                    SCREENING_TOTAL.labels(phase="llm_confirmation", result="blocked").inc()
                    SCREENING_DURATION.labels(phase="llm_confirmation").observe(time.time() - start_time)
                    SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
                    SCREENING_CONFIDENCE.observe(confidence)
                    return ScreeningResult(
                        allowed=False,
                        reason=reason,
                        phase="llm_confirmation",
                        confidence=confidence,
                    )

            except Exception as e:
                logger.error("LLM confirmation failed for skill '%s': %s", skill.name, e)
                # Fail-safe: allow evolution on LLM errors (don't block valid fixes)
                # Metrics
                SCREENING_TOTAL.labels(phase="llm_confirmation", result="allowed").inc()
                SCREENING_DURATION.labels(phase="llm_confirmation").observe(time.time() - start_time)
                SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
                SCREENING_CONFIDENCE.observe(0.0)
                return ScreeningResult(
                    allowed=True,
                    reason=f"LLM confirmation unavailable: {e}",
                    phase="llm_confirmation",
                    confidence=0.0,
                )

        # No screening applied
        SCREENING_TOTAL.labels(phase="none", result="allowed").inc()
        SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
        return ScreeningResult(
            allowed=True,
            reason="No screening applied (DERIVED/CAPTURED or no LLM)",
            phase="none",
            confidence=1.0,
        )

    async def _reject_locked(self, skill_id: str, reason: str, start_time: float) -> ScreeningResult:
        await self._log_rejection_event(skill_id, "locked", reason)
        SCREENING_TOTAL.labels(phase="locked", result="blocked").inc()
        SCREENING_DURATION.labels(phase="locked").observe(time.time() - start_time)
        SCREENING_DURATION.labels(phase="total").observe(time.time() - start_time)
        SCREENING_CONFIDENCE.observe(1.0)
        return ScreeningResult(allowed=False, reason=reason, phase="locked", confidence=1.0)

    async def _log_rejection_event(self, skill_id: str, phase: str, reason: str, confidence: float = 1.0) -> None:
        """Log rejection event to EventLogger if configured.

        Args:
            skill_id: Skill identifier
            phase: Rejection phase (cooldown, llm_confirmation)
            reason: Rejection reason
            confidence: LLM confidence
        """
        if self._event_logger:
            try:
                await self._event_logger.log(
                    "EVOLUTION_REJECTED",
                    {
                        "skill_id": skill_id,
                        "phase": phase,
                        "reason": reason,
                        "confidence": confidence,
                    },
                )
            except Exception as e:
                logger.warning("Failed to log EVOLUTION_REJECTED event: %s", e)
