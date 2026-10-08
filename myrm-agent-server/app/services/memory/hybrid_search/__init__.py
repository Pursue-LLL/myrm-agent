"""Dual-engine hybrid search package.

[POS]
Exports service and dependency injector for dual-engine hybrid search and fallback.

[INPUT]
- .provider.DualEngineHybridSearchService, get_hybrid_search_service

[OUTPUT]
- DualEngineHybridSearchService, get_hybrid_search_service
"""

from __future__ import annotations

from app.services.memory.hybrid_search.provider import (
    DualEngineHybridSearchService,
    get_hybrid_search_service,
)

__all__ = [
    "DualEngineHybridSearchService",
    "get_hybrid_search_service",
]
