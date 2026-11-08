"""LLM integration endpoints.

[OUTPUT]
The APIRouter with every LLM probe endpoint, re-exported for app.api.router and the tests.

[POS]
Aggregate exit of the LLM integration package: one module per probe area, one router for the app.
"""

from __future__ import annotations

from .common import _LOCAL_NO_AUTH_KEY_MARKER, _apply_local_no_auth_marker_transport_overrides, router
from .discovery import (
    ModelDiscoveryRequest,
    ModelDiscoveryResult,
    _build_models_candidates,
    _extract_model_ids,
    _is_loopback_host,
    _is_trusted_split_stack_host,
    _normalize_api_base,
    discover_models,
)
from .model_info import (
    ModelCandidate,
    ModelCapabilities,
    ModelInfoBatchRequest,
    ModelInfoRequest,
    ModelInfoResponse,
    _search_models_by_name,
    get_model_info,
    get_model_info_batch,
)
from .preflight import (
    ModelSwitchPreflightItem,
    ModelSwitchPreflightRequest,
    ModelSwitchPreflightResult,
    _resolve_target_max_input_tokens,
    model_switch_preflight,
)
from .speed_test import (
    SpeedTestItemResult,
    SpeedTestRequest,
    _ttft_sort_key,
    speed_test,
)
from .verify import (
    LLMVerifyData,
    LLMVerifyRequest,
    ReachabilityResult,
    _cache_key,
    _reachability_cache,
    check_model_reachability,
    verify_llm_connection,
)

__all__ = [
    "_resolve_target_max_input_tokens",
    "_ttft_sort_key",
    "_cache_key",
    "_LOCAL_NO_AUTH_KEY_MARKER",
    "_apply_local_no_auth_marker_transport_overrides",
    "_build_models_candidates",
    "_extract_model_ids",
    "_is_loopback_host",
    "_is_trusted_split_stack_host",
    "_search_models_by_name",
    "router",
    "discover_models",
    "verify_llm_connection",
    "check_model_reachability",
    "speed_test",
    "get_model_info",
    "get_model_info_batch",
    "model_switch_preflight",
    "ModelDiscoveryRequest",
    "ModelDiscoveryResult",
    "LLMVerifyRequest",
    "LLMVerifyData",
    "ReachabilityResult",
    "ModelCapabilities",
    "ModelCandidate",
    "ModelInfoResponse",
    "ModelInfoRequest",
    "ModelInfoBatchRequest",
    "ModelSwitchPreflightItem",
    "ModelSwitchPreflightRequest",
    "ModelSwitchPreflightResult",
    "SpeedTestItemResult",
    "SpeedTestRequest",
    "_reachability_cache",
    "_normalize_api_base",
]
