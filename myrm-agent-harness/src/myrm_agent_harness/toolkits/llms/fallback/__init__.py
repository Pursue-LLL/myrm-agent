"""Enhanced model fallback with cooldown and candidate pool.

Provides sophisticated model fallback management with:
- Cooldown period: Temporarily skip failed models
- Candidate pool: Support multiple fallback models

[INPUT]
- llms.errors.classifier (POS: error classification)

[OUTPUT]
- ModelFallbackManager: model fallback manager
- ModelCandidate: model candidate dataclass
- ManagedLLM: LLM wrapper integrating ModelFallbackManager
- HealthProbeResult: structured liveness probe outcome (ok / error_kind / error / latency_ms)
- probe_llm_health: classify a probe failure (timeout vs provider error) instead of flattening it

[POS]
Enhanced model fallback management. Supports cooldown periods and candidate pools.
"""

from .config import PRESET_CONFIGS, ProbeConfig, get_preset_config
from .context import (
    FailoverEmitter,
    failover_emitter_ctx,
    get_active_failover_emitter,
    with_failover_emitter,
)
from .events import FailoverCallback, FailoverEvent, RecoveryCallback, RecoveryEvent
from .health_check import (
    DEFAULT_HEALTH_PROBE_TIMEOUT_S,
    HealthProbeErrorKind,
    HealthProbeResult,
    lightweight_health_check,
    probe_llm_health,
)
from .managed_llm import FallbackModel, ManagedLLM
from .manager import ModelCandidate, ModelFallbackManager
from .probe_throttle import GlobalProbeThrottle, get_global_probe_throttle
from .recommendations import (
    FallbackRecommendation,
    generate_quantified_reason,
    get_primary_recommendation,
    recommend_fallback,
)
from .scenario import ModelMetrics, ScenarioType, select_by_scenario, select_by_scenario_with_quality

__all__ = [
    "DEFAULT_HEALTH_PROBE_TIMEOUT_S",
    "PRESET_CONFIGS",
    "FailoverCallback",
    "FailoverEmitter",
    "FailoverEvent",
    "FallbackModel",
    "FallbackRecommendation",
    "GlobalProbeThrottle",
    "ManagedLLM",
    "HealthProbeErrorKind",
    "HealthProbeResult",
    "ModelCandidate",
    "ModelFallbackManager",
    "ModelMetrics",
    "ProbeConfig",
    "RecoveryCallback",
    "RecoveryEvent",
    "ScenarioType",
    "failover_emitter_ctx",
    "generate_quantified_reason",
    "get_active_failover_emitter",
    "get_global_probe_throttle",
    "get_preset_config",
    "get_primary_recommendation",
    "lightweight_health_check",
    "probe_llm_health",
    "recommend_fallback",
    "select_by_scenario",
    "select_by_scenario_with_quality",
    "with_failover_emitter",
]
