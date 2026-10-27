"""Remote backup storage contract: what a provider offers, whichever provider it is.

[INPUT]
(standard library only)

[OUTPUT]
RemoteBackupStrategy: upload / download / list / delete / check_connection
RemoteBackupFile: one listed backup (name, modified time, size)
RemoteStorageError: the storage answered but refused to list its backups

[POS]
The seam between the backup runner / sync job and a concrete provider (WebDAV, S3). Writes report failure as ``False``.
A listing that cannot be read raises (``RemoteStorageError`` for a refusal, the transport error otherwise) instead of
returning an empty list, so an unreachable remote never looks like one without backups.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class RemoteStorageError(RuntimeError):
    """The remote storage answered, but refused to list its backups."""


@dataclass(frozen=True)
class RemoteBackupFile:
    """Metadata for a remote backup file."""

    file_name: str
    modified_time: datetime
    size_bytes: int


class RemoteBackupStrategy(ABC):
    """Abstract base for remote backup operations."""

    @abstractmethod
    async def upload(self, local_path: Path, remote_name: str) -> bool:
        """Upload a local backup file to remote storage."""

    @abstractmethod
    async def download(self, remote_name: str, local_path: Path) -> bool:
        """Download a remote backup file to local path."""

    @abstractmethod
    async def list_files(self) -> list[RemoteBackupFile]:
        """List all backup files on remote storage, newest first.

        Raises when the storage cannot be read: an unreadable listing must never look like an empty one.
        """

    @abstractmethod
    async def delete(self, remote_name: str) -> bool:
        """Delete a remote backup file."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Test connectivity to remote storage."""
