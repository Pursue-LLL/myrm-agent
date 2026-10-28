"""Ephemeral in-memory credentials subsystem with physical memory zeroization.

[INPUT]
- .types::EphemeralCredential, EphemeralCredentialSummary, command_digest, validate_credential_key
- .store::EphemeralCredentialStore, get_ephemeral_credential_store

[OUTPUT]
- Public exports of the ephemeral credential subsystem.

[POS]
core/security/ephemeral_credentials/__init__.py
Foundation layer security facade.
"""

from __future__ import annotations

from .store import EphemeralCredentialStore, get_ephemeral_credential_store
from .types import (
    EphemeralCredential,
    EphemeralCredentialSummary,
    command_digest,
    validate_credential_key,
)

__all__ = [
    "EphemeralCredential",
    "EphemeralCredentialStore",
    "EphemeralCredentialSummary",
    "command_digest",
    "get_ephemeral_credential_store",
    "validate_credential_key",
]
