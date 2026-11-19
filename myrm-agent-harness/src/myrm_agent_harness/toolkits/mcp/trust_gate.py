"""Host workspace trust gate registry for MCP spawn decisions.

The agent layer owns the gate and registers it at import time; the MCP session
start and the executor transport read it before spawning a stdio server. The
registry lives apart from `transport.py` so that registering the gate does not
import the MCP SDK, which a run only needs once it connects to a server.

[INPUT]
- (none: stdlib only)

[OUTPUT]
- WorkspaceTrustGate: Protocol of the host-provided spawn gate
- set_workspace_trust_gate / get_workspace_trust_gate: register (or clear) and read the gate

[POS]
Registry seam between the agent layer (gate owner) and the MCP toolkit (gate consumer);
toolkits/ never imports agent/ (see toolkits/_ARCH.md).
"""

from typing import Protocol


class WorkspaceTrustGate(Protocol):
    """Host-provided workspace trust gate for MCP spawn decisions.

    Implemented by the agent layer; the toolkit only depends on this
    Protocol so toolkits/ never imports agent/ (see toolkits/_ARCH.md).
    """

    def get_trust_level(self) -> object:
        """Return the current workspace trust level (opaque to the toolkit)."""
        ...

    def assert_mcp_spawn_allowed(
        self,
        *,
        workspace_root: str | None,
        cwd: str | None,
        plugin_root: str | None,
        trust_level: object,
    ) -> None:
        """Raise when spawning an MCP server from the workspace scope is blocked."""
        ...


_trust_gate: WorkspaceTrustGate | None = None


def set_workspace_trust_gate(gate: WorkspaceTrustGate | None) -> None:
    """Register (or clear) the host workspace trust gate. Agent layer owns this."""
    global _trust_gate
    _trust_gate = gate


def get_workspace_trust_gate() -> WorkspaceTrustGate | None:
    """Return the registered host workspace trust gate, if any."""
    return _trust_gate
