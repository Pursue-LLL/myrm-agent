"""Storage components for channel authentication.

[INPUT]

[OUTPUT]
- LoginSessionStore: Temporary session storage (Protocol + InMemory)
- CredentialsStore: Encrypted persistent storage (file-based)

[POS]
Framework layer storage module. Provides out-of-the-box storage implementations
for channel authentication. Business layer can use default implementations or
provide custom backends (e.g., Redis for SaaS).
"""

from __future__ import annotations

from .credentials_store import CredentialsStore
from .login_session_store import InMemorySessionStore, LoginSessionData, LoginSessionStoreProtocol

__all__ = [
    "CredentialsStore",
    "InMemorySessionStore",
    "LoginSessionData",
    "LoginSessionStoreProtocol",
]
