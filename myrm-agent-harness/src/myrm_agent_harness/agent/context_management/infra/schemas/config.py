"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- ContextConfig / DEFAULT_CONTEXT_CONFIG / get_compress_min_save_for_model

[POS]
`infra/schemas/` 的上下文窗口与压缩阈值配置。
"""

from __future__ import annotations

from dataclasses import dataclass

# Minimum compression savings threshold (Prompt Cache protection).
# See CONTEXT_ENGINEERING.md §5.2.
# Assumes T_prefix=30k, T_cleared > T_prefix * (1-P), at 90% discount: 30k * 0.1 = 3k.
# 3000 tokens balances cache protection without being overly conservative.

COMPRESS_MIN_SAVE_DEFAULT: int = 3000


def get_compress_min_save_for_model(model_name: str) -> int:
    """Get compress_min_save value for a given model.

    Currently returns a fixed value; interface reserved for per-provider tuning.

    Args:
        model_name: Model name (e.g. "anthropic/claude-3-opus")

    Returns:
        compress_min_save value (currently fixed at 3000)
    """
    _ = model_name
    return COMPRESS_MIN_SAVE_DEFAULT


@dataclass
class ContextConfig:
    """Context management configuration.

    All thresholds scale dynamically from max_context_tokens using pure proportional ratios.
    When compress_start_ratio is None (default), the classic fixed ratios apply:
    - proactive_reset_threshold = max_context_tokens * 0.4 — summarization starts (early warning)
    - compress_threshold = max_context_tokens * 0.5 — compression starts
    - summarize_trigger_threshold = max_context_tokens * 0.9 — last resort

    When compress_start_ratio is set (range [0.20, 0.85]), thresholds are derived from it
    so that they stay ascending and below the window at any valid ratio:
        proactive_reset = compress_start_ratio
        compress = compress_start_ratio + (0.95 - compress_start_ratio) / 3
        summarize_trigger = 0.95 (hard ceiling)

    Note: summarize_trigger_threshold is the hard ceiling; summarization failure raises and aborts.

    Three-layer context defense:
    1. Filter (instant) — truncate large outputs + smart preview
    2. Compress (in-memory) — triggered at compress_threshold, 3-tier strategy (Dedup/Truncate/Remove)
    3. Summarize (irreversible) — triggered at summarize_trigger_threshold, structured summary

    Example:
        config = ContextConfig(max_context_tokens=128000)   # GPT-4 (128k)
        config = ContextConfig(max_context_tokens=200000)   # Claude Sonnet 4.5 (200k)
        config = ContextConfig(max_context_tokens=1000000)  # DeepSeek V4 Pro (1M)
        config = ContextConfig(max_context_tokens=200000, compress_start_ratio=0.6)  # delayed compression
    """

    max_context_tokens: int

    # Optional user-configurable compression start ratio. When set, overrides the
    # default fixed ratios (see class docstring). Valid range: [0.20, 0.85].
    # None means use default ratios (0.4/0.5/0.9).
    compress_start_ratio: float | None = None

    # Layer 1: single tool result truncation threshold (model-independent)
    tool_result_evict_threshold: int = 5000

    # Minimum compression savings (Prompt Cache protection, model-independent)
    compress_min_save: int = 3000

    # Token budget ratio for tail protection (used in L3 Summarization).
    # Defines the percentage of max_context_tokens to preserve verbatim before compressing.
    tail_budget_ratio: float = 0.20

    # Keep N most recent tool-call groups during Compress (see compactor.py).
    # Filter/ActivePrune use separate thresholds; failed IDs come from compression_intent.
    keep_recent_calls: int = 5

    # Memory forgetting half-life in days. Frontend can tune the agent's forgetting curve.
    time_decay_half_life_days: float = 90.0

    # Summarization inactivity timeout: if no streaming token arrives within this
    # window, the summarization call is considered hung and will be cancelled.
    # The cancelled summarization degrades to deterministic fallback.
    compaction_inactivity_timeout_s: float = 90.0

    # Summarization total ceiling: absolute maximum wall-clock time for a single
    # summarization call. Prevents degenerate trickle streams from holding a turn.
    compaction_total_ceiling_s: float = 600.0

    def _effective_ratio(self) -> float | None:
        """Return clamped compress_start_ratio or None for default behavior."""
        if self.compress_start_ratio is None:
            return None
        return max(0.20, min(0.85, self.compress_start_ratio))

    @property
    def compress_threshold(self) -> int:
        """Compression trigger: 50% of model window (default), or a third of the way from the start ratio to 95%.

        Pure ratio scaling ensures correct behavior for any context window size,
        from 8K edge models to 1M+ large-window models.
        """
        max_tokens = self.max_context_tokens if self.max_context_tokens is not None else 120000
        ratio = self._effective_ratio()
        if ratio is not None:
            gap = (0.95 - ratio) / 3.0
            return int(max_tokens * (ratio + gap))
        return int(max_tokens * 0.5)

    @property
    def proactive_reset_threshold(self) -> int:
        """Proactive reset trigger: 40% of model window (default), or compress_start_ratio.

        Summarization starts at this watermark instead of waiting for the 90% last-resort
        threshold, which keeps the model in its optimal clarity zone — mitigating
        long-conversation degradation, amnesia, and hallucination while flattening API
        token cost from O(n^2) to constant.

        Fires before compress_threshold (50%) as an "early warning" layer.
        """
        max_tokens = self.max_context_tokens if self.max_context_tokens is not None else 120000
        ratio = self._effective_ratio()
        if ratio is not None:
            return int(max_tokens * ratio)
        return int(max_tokens * 0.4)

    @property
    def summarize_trigger_threshold(self) -> int:
        """Summarization trigger (last resort): 95% of window when ratio set, else 90%.

        Reserves 10% of the context window for the compaction summary itself,
        ensuring the compaction mechanism can run even under maximum context
        pressure without running out of output space.
        """
        max_tokens = self.max_context_tokens if self.max_context_tokens is not None else 120000
        ratio = self._effective_ratio()
        if ratio is not None:
            return int(max_tokens * 0.95)
        return int(max_tokens * 0.9)


DEFAULT_CONTEXT_CONFIG = ContextConfig(max_context_tokens=128000)
