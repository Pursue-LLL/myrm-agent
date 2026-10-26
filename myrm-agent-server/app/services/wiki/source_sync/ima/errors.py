"""Typed failures of the Tencent ima OpenAPI lane.

[INPUT]
- (none)

[OUTPUT]
- ImaError hierarchy: each class carries a stable ``kind`` that is persisted in the ledger and mapped to UI copy

[POS]
Failure taxonomy shared by transport, client, content resolution and the sync engine. The engine decides
retry / pause / give-up purely from ``kind`` so no caller inspects message text.
"""

from __future__ import annotations

from typing import ClassVar


class ImaError(Exception):
    """Base class for every ima lane failure."""

    kind: ClassVar[str] = "unknown"

    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ImaAuthError(ImaError):
    """A request was rejected as unauthorized: the key pair is bad, or it works but may not read that one resource.

    ima answers both the same way, so the rejection alone cannot tell them apart; ``SyncContext.require_valid_key`` does.
    """

    kind: ClassVar[str] = "auth"


class ImaRateLimitError(ImaError):
    """The key exceeded its call frequency; retry after a pause."""

    kind: ClassVar[str] = "rate_limit"


class ImaTransientError(ImaError):
    """Network, timeout, 5xx or documented retryable failure; the same call may succeed later."""

    kind: ClassVar[str] = "transient"


class ImaPermanentError(ImaError):
    """The call cannot succeed as issued (bad business code, gone media, untrusted URL)."""

    kind: ClassVar[str] = "permanent"


class ImaPermissionError(ImaPermanentError):
    """The key is valid, yet ima never lets it read this resource (another author's note, a share without access)."""

    kind: ClassVar[str] = "permission"


class ImaTooLargeError(ImaPermanentError):
    """The item exceeds the import size cap."""

    kind: ClassVar[str] = "too_large"


class ImaPageUnavailableError(ImaTransientError):
    """A saved web page could not be fetched from its original address (down, blocked or removed)."""

    kind: ClassVar[str] = "page_unavailable"
