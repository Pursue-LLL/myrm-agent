"""[POS]: app/services/memory/cvfs/__init__.py
[INPUT]: ContextVFSProvider lifecycle manager.
[OUTPUT]: Public exports for context virtual file system services.
"""

from .provider import (
    ContextVFSProvider,
    get_context_vfs,
)

__all__ = [
    "ContextVFSProvider",
    "get_context_vfs",
]
