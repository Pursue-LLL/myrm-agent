"""Local file store of MCP tool tables, one file per server configuration.

[INPUT]
- infra.data_dir::resolve_data_dir (POS: Single entry point for the Myrm state root)
- infra.atomic_write::atomic_write (POS: Atomic file write with crash-consistency guarantee)
- toolkits.mcp.tool_table::ToolTable, encode_table, decode_table (POS: Serializable snapshot of the tools one MCP server exposes)

[OUTPUT]
- ToolTableStore: Reads, writes and drops the table kept for one connection-pool key; keeps the newest entries only

[POS]
Persistence layer of the MCP tool-table cache. Synchronous file I/O: async callers run it in a worker thread. A file that
cannot be read as a table counts as absent, so a damaged cache costs one live discovery and never an error.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from myrm_agent_harness.infra.atomic_write import atomic_write
from myrm_agent_harness.infra.data_dir import resolve_data_dir
from myrm_agent_harness.toolkits.mcp.tool_table import ToolTable, decode_table, encode_table

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 64
"""Tables kept on disk; a changed server configuration is a new key, so old keys would otherwise pile up."""


def _modified_at(path: Path) -> float:
    return path.stat().st_mtime


class ToolTableStore:
    """Tool tables on disk, keyed by the hex digest the connection pool derives from a server configuration."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @classmethod
    def at_state_root(cls) -> ToolTableStore:
        """The store under the process's state root."""
        return cls(resolve_data_dir() / "cache" / "mcp-tool-tables")

    def load(self, key: str) -> ToolTable | None:
        """The table stored under *key*, or ``None`` when there is none or it cannot be read."""
        try:
            return decode_table(self._path(key).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return None

    def save(self, key: str, table: ToolTable) -> None:
        """Replace the table under *key* atomically, then drop the oldest entries beyond the limit.

        A table identical to the stored one is not written again; the entry only counts as used just now.
        """
        text = encode_table(table)
        path = self._path(key)
        try:
            unchanged = path.read_text(encoding="utf-8") == text
        except (OSError, UnicodeDecodeError):
            unchanged = False
        if unchanged:
            os.utime(path)
            return
        atomic_write(path, text)
        self._prune()

    def discard(self, key: str) -> None:
        """Remove the table under *key*."""
        self._path(key).unlink(missing_ok=True)

    def _path(self, key: str) -> Path:
        return self._directory / f"{key}.json"

    def _prune(self) -> None:
        try:
            newest_first = sorted(self._directory.glob("*.json"), key=_modified_at, reverse=True)
            for stale in newest_first[_MAX_ENTRIES:]:
                stale.unlink(missing_ok=True)
        except OSError:
            logger.debug("MCP tool table pruning skipped", exc_info=True)


__all__ = ["ToolTableStore"]
