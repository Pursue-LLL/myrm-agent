"""Mux error classification tokens for the Chrome MCP client."""

from __future__ import annotations

from dev_gate_contract import (
    BENIGN_CLEANUP_TOKENS,
    PAGE_OWNERSHIP_ERROR_TOKENS,
    TRANSIENT_MUX_ERROR_TOKENS,
)


def is_transient_mux_error(message: str) -> bool:
    return any(token in message for token in TRANSIENT_MUX_ERROR_TOKENS)


def is_page_ownership_error_message(message: str) -> bool:
    return any(token in message for token in PAGE_OWNERSHIP_ERROR_TOKENS)


def is_page_ownership_error(exc: BaseException) -> bool:
    return isinstance(exc, RuntimeError) and is_page_ownership_error_message(str(exc))


def is_context_reset_error(exc: BaseException) -> bool:
    if not isinstance(exc, RuntimeError):
        return False
    message = str(exc)
    return "Chrome MCP context reset" in message or "call new_page before" in message


def is_benign_cleanup_error(message: str) -> bool:
    return any(token in message for token in BENIGN_CLEANUP_TOKENS)
