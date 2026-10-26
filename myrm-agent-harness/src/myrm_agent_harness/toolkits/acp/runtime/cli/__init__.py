"""CLI runtime backend — one external CLI agent process per turn, streamed as RuntimeEvents.

[INPUT]
- toolkits.acp.runtime.cli.runtime::CliRuntime (POS: CLI runtime backend — spawns a CLI agent process and parses NDJSON output.) [lazy]

[OUTPUT]
- CliRuntime: lazy-imported RuntimeBackend for CLI agents (Claude Code, Codex, ...)

[POS]
CLI backend of the ACP runtime. Facade of the ``cli`` package, whose modules are imported by their own path.
"""

from __future__ import annotations

__all__ = ["CliRuntime"]


def __getattr__(name: str) -> object:
    if name == "CliRuntime":
        from .runtime import CliRuntime

        globals()[name] = CliRuntime
        return CliRuntime

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
