"""Types and data structures for ephemeral credentials.

[INPUT]
- core.security.process_env.code_injection_env::is_code_injection_env_name (POS: Names that make a program run what the value names)

[OUTPUT]
- EphemeralCredential: Encapsulated credential with physical memory wipe capability.
- EphemeralCredentialSummary: Safe metadata summary without secret exposure.
- SanitizedCredentialKey: Validated environment key safe from shell injection.
- command_digest: The digest a credential is bound to, computed from the command text a person approved.

[POS]
Foundational memory security models in core/security/ephemeral_credentials/.
Depends only on the standard library and the shared code-injection name set; supports ctypes.memset zeroization.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field

from myrm_agent_harness.core.security.process_env.code_injection_env import is_code_injection_env_name

_VALID_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
# Names that shape the shell or the process a command starts in: who runs it, where programs are found, how the shell
# starts and splits words. They are not code-injection names in the shared sense, but no credential belongs under them.
_RESERVED_ENV_KEYS = frozenset(
    {
        "ENV",
        "HOME",
        "IFS",
        "LOGNAME",
        "PATH",
        "PERL5LIB",
        "PROMPT_COMMAND",
        "RUBYLIB",
        "SHELL",
        "USER",
    }
)


def validate_credential_key(key: str) -> str:
    """Validate and sanitize a credential key name.

    Raises:
        ValueError: If the key format is invalid or attempts to poison critical env vars.
    """
    normalized = key.strip().upper()
    if not _VALID_KEY_PATTERN.match(normalized):
        raise ValueError(
            f"Invalid credential key '{key}'. Must start with a letter and contain only alphanumeric characters and underscores (max 64 chars)."
        )
    if normalized in _RESERVED_ENV_KEYS or is_code_injection_env_name(normalized):
        raise ValueError(
            f"Blocked credential key '{key}'. Overriding critical system environment variables is strictly forbidden."
        )
    return normalized


def command_digest(command: str) -> str:
    """Return the digest an ephemeral credential is bound to: the command a person approved, trimmed.

    The approval layer (which stages the credential) and the executor (which consumes it) both call this on the
    command as the agent issued it, so the two sides cannot disagree about which command a credential belongs to.
    """
    return hashlib.sha256(command.strip().encode("utf-8")).hexdigest()


@dataclass
class EphemeralCredential:
    """Ephemeral in-memory credential with physical memory zeroization.

    Stores secret values in a mutable bytearray to allow physical memory clearing
    (overwriting with 0x00 bytes) upon single-use consumption or revocation,
    preventing persistent secrets in process dumps.
    """

    handle_id: str
    session_id: str
    key: str
    _material: bytearray = field(repr=False)
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 60.0
    single_use: bool = True
    is_consumed: bool = False
    expected_action_digest: str | None = None

    @property
    def expires_at(self) -> float:
        """Timestamp when this credential expires."""
        return self.created_at + self.ttl_seconds

    @property
    def is_expired(self) -> bool:
        """Check if credential has exceeded its TTL."""
        return time.time() > self.expires_at

    def read_secret(self) -> str:
        """Read plaintext secret.

        Raises:
            ValueError: If credential has already been wiped or is expired.
        """
        if self.is_consumed and self.single_use:
            raise ValueError(f"Credential '{self.handle_id}' has already been consumed.")
        if self.is_expired:
            raise ValueError(f"Credential '{self.handle_id}' has expired (TTL={self.ttl_seconds}s).")
        if not self._material:
            raise ValueError(f"Credential '{self.handle_id}' has been physically wiped.")
        return self._material.decode("utf-8")

    def wipe(self) -> None:
        """Physically overwrite memory buffer with zeros and clear references."""
        if self._material:
            buf_len = len(self._material)
            if buf_len > 0:
                # In-place physical memory zeroization before resizing
                self._material[:] = b"\x00" * buf_len
            self._material.clear()
        self.is_consumed = True


@dataclass(frozen=True, slots=True)
class EphemeralCredentialSummary:
    """Non-sensitive metadata view of an ephemeral credential for UI display."""

    handle_id: str
    session_id: str
    key: str
    created_at: float
    expires_at: float
    ttl_seconds: float
    single_use: bool
    is_consumed: bool
    is_expired: bool
    expected_action_digest: str | None = None
