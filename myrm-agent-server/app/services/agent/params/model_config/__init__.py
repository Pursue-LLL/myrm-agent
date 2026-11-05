"""[INPUT]
- .resolvers::_resolve_model_config (POS: ModelSelection → ModelConfig)
- .providers (POS: provider id normalization and key lookup)

[OUTPUT]
- _resolve_model_config: the single model-config resolver used by web/channel/cron/voice/eval
- _find_provider_api_key, _resolve_image_api_key_provider, normalize_storage_provider_id,
  LEGACY_STORAGE_PROVIDER_ID_REMAP

[POS]
Aggregate exit of the model-configuration domain: turning a key-free ModelSelection into a concrete
ModelConfig, and resolving the provider row/API key it needs. Kept apart from the request DTOs and
from the conversion stages because every entry point (not just the web converter) resolves models.
"""

from __future__ import annotations

from .providers import (
    LEGACY_STORAGE_PROVIDER_ID_REMAP,
    _find_provider_api_key,
    _resolve_image_api_key_provider,
    normalize_storage_provider_id,
)
from .resolvers import _resolve_model_config

__all__ = [
    "LEGACY_STORAGE_PROVIDER_ID_REMAP",
    "_find_provider_api_key",
    "_resolve_image_api_key_provider",
    "_resolve_model_config",
    "normalize_storage_provider_id",
]
