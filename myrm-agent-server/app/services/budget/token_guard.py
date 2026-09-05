"""Lightweight single-task token budget guard service.

Enforces task-level soft warning and hard cap limits based on official
usage tokens reported by LLM providers, preventing runaway spend.

[INPUT]
- None (POS: Pure dataclass and state manager)

[OUTPUT]
- GuardStatus: Status enum for token limits
- GuardEvaluation: Evaluation result dataclass
- TaskTokenGuard: Single-task token consumption manager
"""

from dataclasses import dataclass
from enum import Enum


class GuardStatus(str, Enum):
    """Status of token consumption relative to configured task limits."""

    NORMAL = "normal"
    WARNING_SOFT_CAP = "warning_soft_cap"
    BREACH_HARD_CAP = "breach_hard_cap"


@dataclass(frozen=True)
class GuardEvaluation:
    """Result of token budget evaluation after an execution turn."""

    status: GuardStatus
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    hard_limit: int | None
    soft_limit: int | None
    is_paused: bool
    message: str | None = None


class TaskTokenGuard:
    """Manages token consumption for a single execution task or session."""

    def __init__(
        self,
        hard_limit: int | None = None,
        soft_limit_ratio: float = 0.8,
    ) -> None:
        self._hard_limit = hard_limit
        self._soft_limit = int(hard_limit * soft_limit_ratio) if hard_limit else None
        self._prompt_tokens = 0
        self._completion_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self._prompt_tokens + self._completion_tokens

    @property
    def prompt_tokens(self) -> int:
        return self._prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self._completion_tokens

    def record_turn_usage(self, prompt_tokens: int, completion_tokens: int) -> GuardEvaluation:
        """Accumulate usage and evaluate budget thresholds."""
        self._prompt_tokens += max(0, prompt_tokens)
        self._completion_tokens += max(0, completion_tokens)
        total = self.total_tokens

        if self._hard_limit and total >= self._hard_limit:
            return GuardEvaluation(
                status=GuardStatus.BREACH_HARD_CAP,
                total_tokens=total,
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                hard_limit=self._hard_limit,
                soft_limit=self._soft_limit,
                is_paused=True,
                message=f"Task token consumption ({total}) reached or exceeded hard limit ({self._hard_limit}).",
            )

        if self._soft_limit and total >= self._soft_limit:
            return GuardEvaluation(
                status=GuardStatus.WARNING_SOFT_CAP,
                total_tokens=total,
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                hard_limit=self._hard_limit,
                soft_limit=self._soft_limit,
                is_paused=False,
                message=f"Task token consumption ({total}) reached soft warning threshold ({self._soft_limit}).",
            )

        return GuardEvaluation(
            status=GuardStatus.NORMAL,
            total_tokens=total,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            hard_limit=self._hard_limit,
            soft_limit=self._soft_limit,
            is_paused=False,
        )

    def grant_extension(self, additional_tokens: int) -> None:
        """Allow explicit user override to extend the hard limit."""
        if self._hard_limit is not None and additional_tokens > 0:
            self._hard_limit += additional_tokens
            if self._soft_limit is not None:
                self._soft_limit = int(self._hard_limit * 0.8)
