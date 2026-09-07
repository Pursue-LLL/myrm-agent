"""Burn-rate smoke alarm detector for LLM token usage spikes.

Maintains a sliding window of recent token completions across sessions,
calculating deterministic consumption slopes (tokens/minute) to alert
before runaway loops cause catastrophic billing spikes.

[INPUT]
- session_id: str
- tokens: int (consumed tokens delta)

[OUTPUT]
- SmokeAlarmVerdict: dataclass indicating alert state, current burn rate, and reasons.

[POS]
app.services.observability.burn_rate_smoke_alarm
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Final

_DEFAULT_WINDOW_SECONDS: Final[float] = 60.0
_DEFAULT_THRESHOLD_TPM: Final[float] = 100_000.0  # 100k tokens per minute slope


@dataclass(frozen=True, slots=True)
class TokenUsagePoint:
    """A timestamped token consumption record."""

    timestamp: float
    tokens: int


@dataclass(frozen=True, slots=True)
class SmokeAlarmVerdict:
    """Result of burn-rate slope analysis."""

    is_alert: bool
    tokens_per_minute: float
    window_seconds: float
    total_tokens_in_window: int
    threshold_tpm: float
    reason: str


class BurnRateSmokeAlarmDetector:
    """In-memory sliding-window token burn rate detector with microsecond slope calculation."""

    def __init__(
        self,
        *,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
        threshold_tpm: float = _DEFAULT_THRESHOLD_TPM,
    ) -> None:
        self._window_seconds = window_seconds
        self._threshold_tpm = threshold_tpm
        self._sessions: dict[str, deque[TokenUsagePoint]] = {}

    def record_usage(
        self,
        session_id: str,
        tokens: int,
        timestamp: float | None = None,
    ) -> SmokeAlarmVerdict:
        """Record token consumption delta and check for burn rate smoke alarm."""
        if tokens <= 0:
            return self.check_verdict(session_id)

        now = timestamp if timestamp is not None else time.monotonic()
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=200)

        queue = self._sessions[session_id]
        queue.append(TokenUsagePoint(timestamp=now, tokens=tokens))

        # Evict stale entries outside the sliding window
        self._prune_stale(queue, now)
        return self._evaluate_verdict(queue)

    def check_verdict(self, session_id: str | None = None) -> SmokeAlarmVerdict:
        """Evaluate current burn rate slope without adding new usage points."""
        now = time.monotonic()
        if session_id is not None:
            queue = self._sessions.get(session_id)
            if not queue:
                return SmokeAlarmVerdict(
                    is_alert=False,
                    tokens_per_minute=0.0,
                    window_seconds=self._window_seconds,
                    total_tokens_in_window=0,
                    threshold_tpm=self._threshold_tpm,
                    reason="No usage records in window",
                )
            self._prune_stale(queue, now)
            if not queue:
                self._sessions.pop(session_id, None)
                return SmokeAlarmVerdict(
                    is_alert=False,
                    tokens_per_minute=0.0,
                    window_seconds=self._window_seconds,
                    total_tokens_in_window=0,
                    threshold_tpm=self._threshold_tpm,
                    reason="No usage records in window",
                )
            return self._evaluate_verdict(queue)

        # Global aggregate evaluation across all active sessions
        all_points: list[TokenUsagePoint] = []
        for sid, q in list(self._sessions.items()):
            self._prune_stale(q, now)
            if not q:
                self._sessions.pop(sid, None)
            else:
                all_points.extend(q)

        all_points.sort(key=lambda p: p.timestamp)
        return self._evaluate_verdict(all_points)

    def get_active_alerts(self) -> list[dict[str, object]]:
        """Return all sessions currently exceeding the burn rate threshold."""
        now = time.monotonic()
        alerts: list[dict[str, object]] = []
        for sid, q in list(self._sessions.items()):
            self._prune_stale(q, now)
            if not q:
                self._sessions.pop(sid, None)
                continue
            verdict = self._evaluate_verdict(q)
            if verdict.is_alert:
                alerts.append(
                    {
                        "session_id": sid,
                        "tokens_per_minute": verdict.tokens_per_minute,
                        "total_tokens": verdict.total_tokens_in_window,
                        "reason": verdict.reason,
                    }
                )
        return alerts

    def reset(self, session_id: str | None = None) -> None:
        """Clear usage history for a specific session or globally."""
        if session_id is not None:
            self._sessions.pop(session_id, None)
        else:
            self._sessions.clear()

    def _prune_stale(
        self, queue: deque[TokenUsagePoint] | list[TokenUsagePoint], now: float
    ) -> None:
        cutoff = now - self._window_seconds
        if isinstance(queue, deque):
            while queue and queue[0].timestamp < cutoff:
                queue.popleft()

    def _evaluate_verdict(
        self,
        points: deque[TokenUsagePoint] | list[TokenUsagePoint],
    ) -> SmokeAlarmVerdict:
        if not points:
            return SmokeAlarmVerdict(
                is_alert=False,
                tokens_per_minute=0.0,
                window_seconds=self._window_seconds,
                total_tokens_in_window=0,
                threshold_tpm=self._threshold_tpm,
                reason="No active consumption in window",
            )

        total_tokens = sum(p.tokens for p in points)
        span = max(points[-1].timestamp - points[0].timestamp, 1.0)
        tpm = (total_tokens / span) * 60.0

        is_alert = bool(tpm >= self._threshold_tpm and total_tokens >= 20_000)
        reason = (
            f"Burn rate slope ({tpm:.0f} tokens/min) exceeded threshold "
            f"({self._threshold_tpm:.0f} tokens/min)"
            if is_alert
            else "Normal token consumption rate"
        )

        return SmokeAlarmVerdict(
            is_alert=is_alert,
            tokens_per_minute=round(tpm, 1),
            window_seconds=self._window_seconds,
            total_tokens_in_window=total_tokens,
            threshold_tpm=self._threshold_tpm,
            reason=reason,
        )


# Global singleton instance for server-wide smoke alarm tracking
smoke_alarm_detector = BurnRateSmokeAlarmDetector()
