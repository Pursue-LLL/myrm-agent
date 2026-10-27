"""Remote backup storage providers: the shared contract plus the WebDAV and S3 implementations.

[INPUT]
- app.services.memory.backup.remote_sync.storage.base (POS: provider contract)
- app.services.memory.backup.remote_sync.storage.webdav / s3 (POS: the two providers)

[OUTPUT]
- RemoteBackupStrategy / RemoteBackupFile / RemoteStorageError: the contract the runner and the sync job depend on
- WebDAVBackupConfig / WebDAVBackupStrategy, S3BackupConfig / S3BackupStrategy: the providers

[POS]
Everything that talks to a user-owned storage. Callers never see ``httpx`` or ``aioboto3``. See _ARCH.md.
"""

from app.services.memory.backup.remote_sync.storage.base import (
    RemoteBackupFile,
    RemoteBackupStrategy,
    RemoteStorageError,
)
from app.services.memory.backup.remote_sync.storage.s3 import S3BackupConfig, S3BackupStrategy
from app.services.memory.backup.remote_sync.storage.webdav import WebDAVBackupConfig, WebDAVBackupStrategy

__all__ = [
    "RemoteBackupFile",
    "RemoteBackupStrategy",
    "RemoteStorageError",
    "S3BackupConfig",
    "S3BackupStrategy",
    "WebDAVBackupConfig",
    "WebDAVBackupStrategy",
]
