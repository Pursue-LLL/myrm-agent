"""Shared constants for BashExecutor mixins.

[INPUT]
- None

[OUTPUT]
- MCP_MIN_TIMEOUT: Minimum bash timeout when MCP skill IPC is active
- MCP_HOST_MARGIN_SECONDS: How far the host outlives the longest MCP tool-call limit of the skill

[POS]
Internal constants module; MCP_MIN_TIMEOUT is re-exported as _MCP_MIN_TIMEOUT from bash_executor aggregate.
"""

from __future__ import annotations

# A script that uses MCP gets at least this long: IPC and network round-trips are part of its work.
MCP_MIN_TIMEOUT = 120

# Each layer must end after the one inside it: the session actor ends a tool call at the server's ``execute_timeout``,
# the IPC backstop sits ``BACKSTOP_MARGIN_SECONDS`` above that, and the host must outlive both so the error naming the
# stuck tool reaches the script before the process is killed.
MCP_HOST_MARGIN_SECONDS = 30
