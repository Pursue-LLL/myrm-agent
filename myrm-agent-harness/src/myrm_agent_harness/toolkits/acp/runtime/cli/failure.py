"""Failure classification — what went wrong in a finished CLI attempt, from the CLI's own words.

A CLI reports failure in three ways: its final ``result`` line (Claude), a ``turn.failed`` event (Codex, surfaced
by the parser as it streams) and, last, a non-zero exit code. The first is the most specific, so it names the
error code and supplies the message; the exit code alone is only a crash, explained by the CLI's last ``error``
line when it printed one and by the tail of its stderr otherwise.

[INPUT]
- toolkits.acp.runtime.cli.turn_parser::CliResult (POS: the CLI's own verdict on a finished turn)
- toolkits.acp.types::AcpError, AcpErrorCode (POS: ACP runtime type definitions layer.)

[OUTPUT]
- classify_failure: the AcpError of a finished attempt, or None when it succeeded

[POS]
Error vocabulary of CliRuntime. Messages are the CLI's own text, never advice about product settings.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import CliResult
from myrm_agent_harness.toolkits.acp.types import AcpError, AcpErrorCode

_DETAIL_CHARS = 500
# Claude's own category for a login that is missing or was rejected (HTTP 401 and 403, or no API call at all).
_AUTH_ERROR = "authentication_failed"
_UNAUTHORIZED = (401, 403)
_RATE_LIMITED = 429
_SERVER_ERROR = 500


def _from_result(result: CliResult) -> AcpError:
    status = result.api_error_status
    message = result.message or "The CLI reported an error"
    if result.subtype == "error_max_turns" or result.terminal_reason == "max_turns":
        return AcpError(AcpErrorCode.MAX_TURNS, message)
    if result.assistant_error == _AUTH_ERROR or status in _UNAUTHORIZED:
        return AcpError(AcpErrorCode.AUTH_FAILED, message)
    if status == _RATE_LIMITED:
        return AcpError(AcpErrorCode.RATE_LIMITED, message, retryable=True)
    return AcpError(AcpErrorCode.UNKNOWN, message, retryable=status is not None and status >= _SERVER_ERROR)


def classify_failure(
    *,
    result: CliResult | None,
    returncode: int,
    stderr: str,
    killed: bool,
    notice: str = "",
) -> AcpError | None:
    """The error of a finished attempt, or None when it succeeded.

    ``killed`` is a process this runtime stopped itself (cancel, timeout, shutdown): its exit code says nothing
    about the CLI, so it is reported as a cancellation and never as a crash. ``notice`` is the text of the last
    ``error`` line the CLI printed.
    """
    if killed:
        return AcpError(AcpErrorCode.CANCELLED, "The CLI process was stopped before it finished")
    if result is not None and result.is_error:
        return _from_result(result)
    if returncode != 0:
        detail = (notice or stderr).strip()[:_DETAIL_CHARS]
        message = f"CLI process exited with code {returncode}" + (f": {detail}" if detail else "")
        return AcpError(AcpErrorCode.PROCESS_CRASHED, message, retryable=True)
    return None
