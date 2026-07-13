"""Storage components for channel authentication.

[INPUT]

[OUTPUT]
- LoginSessionStore: Temporary session storage (Protocol + InMemory)
- CredentialsStore: Encrypted persistent storage (file-based)
- session_store / get_login_session_store: Process-wide login session singleton

[POS]
Framework layer storage module. Provides out-of-the-box storage implementations
for channel authentication. Business layer can use default implementations or
provide custom backends (e.g., Redis for SaaS).
"""

from __future__ import annotations

from .credentials_store import CredentialsStore
from .login_session_registry import get_login_session_store, session_store
from .login_session_store import InMemorySessionStore, LoginSessionData, LoginSessionStoreProtocol

__all__ = [
    "CredentialsStore",
    "InMemorySessionStore",
    "LoginSessionData",
    "LoginSessionStoreProtocol",
    "get_login_session_store",
    "session_store",
]
