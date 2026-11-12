"""Storage components for channel authentication.

[INPUT]
- app.channels.storage.credentials_store::CredentialsStore (POS: Framework-layer storage component that provides out-of-the-box encrypted file storage for channel credentials.)
- app.channels.storage.login_session_registry::get_login_session_store, session_store (POS: Login-session registry of channels/storage, shared by the API and the lifecycle (the lifecycle must not depend on app.api).)
- app.channels.storage.login_session_store::InMemorySessionStore, LoginSessionData, LoginSessionStoreProtocol (POS: Framework-layer storage component that provides out-of-the-box session management for the async login protocol.)

[OUTPUT]
- LoginSessionStoreProtocol, InMemorySessionStore, LoginSessionData: Temporary login session storage (protocol, in-memory implementation and session record)
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
