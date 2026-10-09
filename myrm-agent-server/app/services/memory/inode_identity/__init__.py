"""[POS]: app/services/memory/inode_identity/__init__.py
[INPUT]: provider.py
[OUTPUT]: InodeIdentityProvider, get_inode_identity_provider
"""

from __future__ import annotations

from app.services.memory.inode_identity.provider import (
    InodeIdentityProvider,
    get_inode_identity_provider,
)

__all__ = [
    "InodeIdentityProvider",
    "get_inode_identity_provider",
]
