# loop_guard/

## Overview
Unified inefficiency detection for Agent sessions — repetition, ping-pong,
no-progress, divergence, output diminishing, and cross-tool error signature
repetition. Provides WARN/BREAK verdicts with context-aware suggestions.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports public API (LoopGuard, DEFAULT_ROUND_BUDGET, types, suggestions). | — |
| guard.py | Core | Session-level LoopGuard with BREAK/WARN/ALLOW verdicts, loop pattern metadata, smart suggestions, metrics, quality feedback, sandbox_boundary_triggered flag, unattended_mode circuit breaker, reset(preserve_call_window=True) for HITL resume, and iteration-budget nudges (warn at 70%, critical at 90% of the run's `round_budget`; `DEFAULT_ROUND_BUDGET` when none is given). A round is one model response: `pre_check(round_id=...)` counts calls that share an id once, and each nudge is given once; the nudge verdicts carry `loop_kind=ITERATION_BUDGET_KIND`, so a consumer can tell them from loop warnings. The guard never ends a run on the budget — the graph's step limit does — and `reset()` restarts the rounds. | ✅ |
| detectors.py | Core | Mixin providing detection algorithms (repetition, ping-pong, no-progress, divergence, output-diminishing, consecutive-failures, error-signature). Raises RunawayCircuitBreakException in unattended mode. Inherited by LoopGuard. | ✅ |
| types.py | Config | Core types — LoopAction, LoopVerdict, LoopKind, ITERATION_BUDGET_KIND (the `loop_kind` of the budget nudges, which are not loop patterns), AgentPhase, SuccessLevel, WarningLevel, ErrorPattern, ToolGroup, VerificationCategory, LoopGuardMetrics, CallRecord. | ✅ |
| stats.py | Core | Optional persistent statistics layer. Records loop events to SQLite for data-driven threshold tuning. | ✅ |

| Submodule | Description |
|-----------|-------------|
| suggestions/ | Context-aware suggestion generation — 16 tools across 8 specialized modules. |

## Key Dependencies

- `core/security` (indirectly, via parent guards)
