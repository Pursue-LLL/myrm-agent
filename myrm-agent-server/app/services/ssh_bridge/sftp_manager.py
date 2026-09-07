"""SFTP File Management service for directory browsing and bi-directional transfer.

[INPUT]
- .models::SSHHostAsset, SFTPItemInfo
- .pool::SSHConnectionPool
- asyncio, logging, pathlib, re

[OUTPUT]
- SFTPManager: Provides list_dir, read_remote_file, and upload_file capabilities over SSH/SFTP.

[POS]
Domain service in app/services/ssh_bridge/sftp_manager.py.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from .models import SFTPItemInfo, SSHHostAsset
from .pool import SSHConnectionPool

logger = logging.getLogger("myrm.services.ssh_bridge.sftp_manager")


class SFTPManager:
    """Provides high-level filesystem operations over remote SSH hosts."""

    def __init__(self, connection_pool: SSHConnectionPool) -> None:
        self._pool = connection_pool
        self._mock_sftp_lister: Optional[Callable[[SSHHostAsset, str], List[SFTPItemInfo]]] = None

    def set_mock_lister(self, lister: Optional[Callable[[SSHHostAsset, str], List[SFTPItemInfo]]]) -> None:
        """Set custom mock directory lister for testing."""
        self._mock_sftp_lister = lister

    async def list_directory(self, host: SSHHostAsset, remote_path: str = ".") -> List[SFTPItemInfo]:
        """List files and folders in the remote directory."""
        if self._mock_sftp_lister:
            return self._mock_sftp_lister(host, remote_path)

        # Use robust POSIX ls -la formatting via SSH
        cmd = f"ls -la --time-style=+%s {remote_path}"
        result = await self._pool.execute_command(host, cmd)

        if result.exit_code != 0:
            logger.warning("SFTP list failed on %s:%s - %s", host.host_id, remote_path, result.stderr)
            return []

        items: List[SFTPItemInfo] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("total "):
                continue

            # Example: drwxr-xr-x 2 root root 4096 1725732100 filename
            parts = line.split(maxsplit=6)
            if len(parts) >= 7:
                perms = parts[0]
                is_dir = perms.startswith("d")
                try:
                    size_bytes = int(parts[4])
                except ValueError:
                    size_bytes = 0
                try:
                    mtime = int(parts[5])
                except ValueError:
                    mtime = 0
                name = parts[6]

                if name in (".", ".."):
                    continue

                full_p = f"{remote_path.rstrip('/')}/{name}" if remote_path != "." else name
                items.append(
                    SFTPItemInfo(
                        filename=name,
                        path=full_p,
                        is_dir=is_dir,
                        size_bytes=size_bytes,
                        mtime=mtime,
                        permissions=perms,
                    )
                )

        return items

    async def read_remote_file_tail(
        self,
        host: SSHHostAsset,
        remote_path: str,
        lines: int = 100,
    ) -> str:
        """Fetch trailing lines of a remote file safely."""
        cmd = f"tail -n {lines} {remote_path}"
        result = await self._pool.execute_command(host, cmd)
        return result.stdout if result.exit_code == 0 else f"Error reading file: {result.stderr}"
