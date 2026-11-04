"""MCP error-handling types.

[INPUT]
- (none)

[OUTPUT]
- MCPRuntimePostureError: Raised when runtime surface scan blocks MCP tool registration.
- MCPToolFailure: A tool-call failure rendered as text for the model; a marked ``str``.

[POS]
MCP-specific error types. `reraise_if_cancelled` stays out of here: `utils.runtime.cancellation` owns the
cancellation rule because both `toolkits.mcp` and `agent.middlewares` consume it, and a rule shared by two packages
cannot be hosted by either. Only types that are MCP's own belong in this module.
"""

from __future__ import annotations


class MCPRuntimePostureError(RuntimeError):
    """Runtime MCP instructions/tool descriptions failed security posture."""

    def __init__(self, message: str, *, server_name: str) -> None:
        super().__init__(message)
        self.server_name = server_name


class MCPToolFailure(str):
    """Failure text for the model that a non-model caller must not mistake for a result.

    ``wrap_tools_with_timeout`` turns timeouts, unsupported content and lost authorization into text, which is what
    a model needs to read. A Python script reaching the same tool through the IPC proxy needs an error instead, and
    cannot tell this text from a real result by its content. Being a ``str`` keeps every model-facing consumer
    (message content, serialization, logging) unchanged.
    """

    __slots__ = ()
