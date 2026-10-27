"""In-memory remote backup storage for tests without WebDAV/S3.

[SCOPE]
A real ``RemoteBackupStrategy`` that keeps uploaded files in a dict, so scheduler and restore
tests exercise the production code path end to end. ``fail_upload`` rejects every upload;
``fail_count`` rejects only the first N attempts, to drive the retry logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.services.memory.backup.remote_sync.storage import RemoteBackupFile, RemoteBackupStrategy


class InMemoryBackupStrategy(RemoteBackupStrategy):
    def __init__(self, *, fail_upload: bool = False, fail_count: int = 0) -> None:
        self._storage: dict[str, bytes] = {}
        self._fail_upload = fail_upload
        self._fail_count = fail_count
        self._upload_attempts = 0

    async def upload(self, local_path: Path, remote_name: str) -> bool:
        self._upload_attempts += 1
        if self._fail_upload:
            return False
        if self._fail_count > 0 and self._upload_attempts <= self._fail_count:
            return False
        self._storage[remote_name] = local_path.read_bytes()
        return True

    async def download(self, remote_name: str, local_path: Path) -> bool:
        if remote_name not in self._storage:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self._storage[remote_name])
        return True

    async def list_files(self) -> list[RemoteBackupFile]:
        results = [
            RemoteBackupFile(file_name=name, modified_time=datetime.now(UTC), size_bytes=len(data))
            for name, data in self._storage.items()
        ]
        results.sort(key=lambda f: f.file_name, reverse=True)
        return results

    async def delete(self, remote_name: str) -> bool:
        if remote_name in self._storage:
            del self._storage[remote_name]
            return True
        return False

    async def check_connection(self) -> bool:
        return True
