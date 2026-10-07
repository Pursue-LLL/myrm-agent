"""Package entrypoint for zero-hallucination memory diagnostics service.

[POS]
app/services/memory/zero_hallucination/__init__.py
Exposes the zero-hallucination singleton service and factory function.

[INPUT]
- .service: ZeroHallucinationMemoryService, get_zero_hallucination_service

[OUTPUT]
- ZeroHallucinationMemoryService, get_zero_hallucination_service
"""

from __future__ import annotations

from app.services.memory.zero_hallucination.service import (
    ZeroHallucinationMemoryService,
    get_zero_hallucination_service,
)

__all__ = [
    "ZeroHallucinationMemoryService",
    "get_zero_hallucination_service",
]
