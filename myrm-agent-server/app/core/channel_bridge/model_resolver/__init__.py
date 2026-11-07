"""Model resolution and custom pricing registration.

[INPUT]
- .resolve / .pricing / .enrich / .common (POS: resolver stages)

[OUTPUT]
- the original public surface plus the helper names existing callers/tests import

[POS]
Aggregate exit of the model resolver package; import path unchanged.
"""

from __future__ import annotations

from .common import (
    _LOCAL_NO_AUTH_API_KEY_MARKER as _LOCAL_NO_AUTH_API_KEY_MARKER,
)
from .common import (
    _OPENAI_LIKE_TYPES as _OPENAI_LIKE_TYPES,
)
from .common import (
    _PLATFORM_MANAGED_KEY as _PLATFORM_MANAGED_KEY,
)
from .common import (
    _PROVIDER_API_BASES as _PROVIDER_API_BASES,
)
from .common import (
    _build_platform_headers as _build_platform_headers,
)
from .common import (
    _build_provider_type_map as _build_provider_type_map,
)
from .common import (
    _build_transport_headers as _build_transport_headers,
)
from .common import (
    _collapse_repeated_prefixes as _collapse_repeated_prefixes,
)
from .common import (
    _extract_active_key,
    _extract_all_active_keys,
    _to_litellm_model,
)
from .common import (
    _is_loopback_api_url as _is_loopback_api_url,
)
from .common import (
    _normalize_model_name as _normalize_model_name,
)
from .common import (
    _parse_litellm_model as _parse_litellm_model,
)
from .common import (
    _supports_provider_no_auth as _supports_provider_no_auth,
)
from .enrich import (
    _lookup_custom_model_info as _lookup_custom_model_info,
)
from .enrich import (
    _resolve_model_max_input_tokens as _resolve_model_max_input_tokens,
)
from .enrich import (
    _resolve_supports_vision_from_litellm as _resolve_supports_vision_from_litellm,
)
from .enrich import (
    enrich_model_capabilities,
    enrich_model_context_window,
)
from .pricing import (
    register_custom_model_pricing,
)
from .resolve import (
    _fallback_model_from_providers,
    resolve_model_config,
)
from .resolve import (
    _resolve_override as _resolve_override,
)
from .resolve import (
    validate_model_override as validate_model_override,
)

__all__ = [
    "resolve_model_config",
    "register_custom_model_pricing",
    "enrich_model_context_window",
    "enrich_model_capabilities",
    "_fallback_model_from_providers",
    "_extract_active_key",
    "_extract_all_active_keys",
    "_to_litellm_model",
]
