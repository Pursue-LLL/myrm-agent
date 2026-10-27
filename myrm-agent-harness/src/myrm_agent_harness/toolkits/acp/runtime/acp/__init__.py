"""ACP runtime backend — one persistent external ACP agent process, driven over the ACP JSON-RPC protocol.

[INPUT]
- toolkits.acp.runtime.acp.runtime::AcpRuntime (POS: ACP protocol runtime backend — spawns an ACP-compatible agent process and speaks JSON-RPC over stdin/stdout.) [lazy]

[OUTPUT]
- AcpRuntime: lazy-imported RuntimeBackend for ACP agents (Claude Code, Codex CLI, ...)

[POS]
ACP backend of the runtime layer. Facade of the ``acp`` package, whose modules are imported by their own path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runtime import AcpRuntime

__all__ = ["AcpRuntime"]


def __getattr__(name: str) -> object:
    if name == "AcpRuntime":
        from .runtime import AcpRuntime

        globals()[name] = AcpRuntime
        return AcpRuntime

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
