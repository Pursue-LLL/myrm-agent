"""Global provider registry with lazy initialization of built-in providers.

[INPUT]
- (none)

[OUTPUT]
- get_registry: Return the global provider registry, creating it lazily on first access.

[POS]
Global provider registry with lazy initialization of built-in providers.
"""

from __future__ import annotations

import importlib
import logging
from typing import Final

from .base import ProviderRegistry

logger = logging.getLogger(__name__)

# ``module:Class`` references spelled out in full: static reachability analysis follows these literals
# (a relative name assembled at runtime is invisible to it), and the lazy import keeps a missing optional
# dependency of one provider from breaking the others.
_BUILTIN_PROVIDERS: Final = (
    "myrm_agent_harness.toolkits.llms.video.providers.openai_provider:OpenAISoraProvider",
    "myrm_agent_harness.toolkits.llms.video.providers.google_provider:GoogleVeoProvider",
    "myrm_agent_harness.toolkits.llms.video.providers.qwen_provider:QwenVideoProvider",
    "myrm_agent_harness.toolkits.llms.video.providers.minimax_provider:MiniMaxVideoProvider",
    "myrm_agent_harness.toolkits.llms.video.providers.xai_provider:XAIGrokProvider",
    "myrm_agent_harness.toolkits.llms.video.providers.fal_provider:FalVideoProvider",
    "myrm_agent_harness.toolkits.llms.video.providers.volcengine_provider:VolcengineSeedanceProvider",
)

_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Return the global provider registry, creating it lazily on first access.

    Built-in providers are registered here. Import errors (missing optional
    dependencies) are logged as warnings, not raised.
    """
    global _registry
    if _registry is not None:
        return _registry

    _registry = ProviderRegistry()
    for reference in _BUILTIN_PROVIDERS:
        _register_builtin(_registry, reference)

    logger.info("Video provider registry initialized with %d providers", len(_registry))
    return _registry


def _register_builtin(registry: ProviderRegistry, reference: str) -> None:
    """Import and register one built-in provider given as ``module:Class``, tolerating import failures."""
    module_path, _, class_name = reference.partition(":")
    try:
        provider_class = getattr(importlib.import_module(module_path), class_name)
        registry.register(provider_class())
    except Exception:
        logger.warning("Failed to register built-in video provider '%s'", class_name, exc_info=True)
