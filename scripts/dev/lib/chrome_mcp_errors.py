"""Mux error classification tokens for the Chrome MCP client."""

from __future__ import annotations

_BENIGN_CLEANUP_TOKENS = (
    "No target with given id",
    "LEASE_NOT_ACTIVE",
    "LEASE_NOT_FOUND",
    "Target closed",
    "detached Frame",
    "No page found",
)
_TRANSIENT_MUX_ERROR_TOKENS = (
    "page has been closed",
    "Target closed",
    "Target.attachToTarget",
    "No target with given id",
    "No page found",
    "upstream terminated",
    "MUX_NOT_READY",
    "main frame too early",
    "Chrome MCP connection reset during",
    "Chrome MCP reconnect queue is full",
    "retry this call",
)
_PAGE_OWNERSHIP_ERROR_TOKENS = (
    "not owned by this shim session",
    "Chrome MCP context reset",
    "call new_page before",
)


def is_transient_mux_error(message: str) -> bool:
    return any(token in message for token in _TRANSIENT_MUX_ERROR_TOKENS)


def is_page_ownership_error_message(message: str) -> bool:
    return any(token in message for token in _PAGE_OWNERSHIP_ERROR_TOKENS)


def is_page_ownership_error(exc: BaseException) -> bool:
    return isinstance(exc, RuntimeError) and is_page_ownership_error_message(str(exc))


def is_context_reset_error(exc: BaseException) -> bool:
    if not isinstance(exc, RuntimeError):
        return False
    message = str(exc)
    return "Chrome MCP context reset" in message or "call new_page before" in message


def is_benign_cleanup_error(message: str) -> bool:
    return any(token in message for token in _BENIGN_CLEANUP_TOKENS)
