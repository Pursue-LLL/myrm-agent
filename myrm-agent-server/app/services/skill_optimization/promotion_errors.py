"""Promotion gate errors for skill optimization."""

from __future__ import annotations

from myrm_agent_harness.agent.skills.evolution.core.promotion_gate import PromotionVerdictResult


class PromotionGateError(Exception):
    """Raised when regression gate blocks version promotion."""

    def __init__(self, verdict: PromotionVerdictResult) -> None:
        self.verdict = verdict
        super().__init__(verdict.message)
