"""[POS]: app/services/memory/context_ingestion/__init__.py
[INPUT]: ContextIngestionProvider lifecycle manager.
[OUTPUT]: Public exports for context ingestion services.
"""

from .provider import (
    ContextIngestionProvider,
    get_context_ingestion_gateway,
)

__all__ = [
    "ContextIngestionProvider",
    "get_context_ingestion_gateway",
]
