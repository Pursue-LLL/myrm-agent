"""Video provider listing for Agent integration.

[INPUT]
- models::VideoGenerationConfig (POS: shared video engine configuration)
- providers::ProviderRegistry, get_registry (POS: the video providers and their models)

[OUTPUT]
- VideoGenerationTools: Lists the video providers and models an agent can use

[POS]
Synchronous part of the video tool: provider discovery. Generation itself is the asynchronous task path
(``async_video_engine`` enqueues, a worker runs ``VideoGenerator``), so nothing here generates.
"""

from __future__ import annotations

import json

from .models import VideoGenerationConfig
from .providers import ProviderRegistry, get_registry


class VideoGenerationTools:
    """Video provider discovery for Agent integration."""

    __slots__ = ("_config", "_registry")

    def __init__(self, config: VideoGenerationConfig, registry: ProviderRegistry | None = None) -> None:
        self._config = config
        self._registry = registry or get_registry()

    def list_providers(self) -> str:
        """JSON of every registered provider with its models and per-mode capabilities."""
        return json.dumps(
            {
                "providers": self._registry.list_providers(),
                "active_provider": self._config.provider,
                "active_model": self._config.model,
            },
            ensure_ascii=False,
        )
