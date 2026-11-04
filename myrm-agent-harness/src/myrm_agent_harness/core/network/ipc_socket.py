"""IPC socket path and permission policy shared by the MCP transport.

[OUTPUT]
- execution_ipc_socket_path: Fresh socket path for one script execution, inside a private per-process directory.
- SOCKET_DIR_MODE / SOCKET_FILE_MODE: Owner-only modes for the dir and socket.

[POS]
Leaf module with no project imports: the MCP IPC server and the helper that ties its lifetime to one
execution share the path and permission policy, and neither should depend on the other for it.
"""

from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

SOCKET_DIR_MODE = 0o700
SOCKET_FILE_MODE = 0o600


def execution_ipc_socket_path() -> str:
    """Return a socket path no other execution uses.

    A shared, predictable ``/tmp/<name>/mcp.sock`` lets another local user pre-create the socket or
    connect to it. The directory is keyed by PID and kept owner-only; the file name is random so two
    executions of one process never collide. The name stays short: AF_UNIX paths are limited to
    about 100 bytes and the temp directory on macOS already takes half of that.
    """
    return str(Path(tempfile.gettempdir()) / f"myrm-agent-mcp-{os.getpid()}" / f"{secrets.token_hex(6)}.sock")


__all__ = ["SOCKET_DIR_MODE", "SOCKET_FILE_MODE", "execution_ipc_socket_path"]
