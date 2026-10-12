"""Remote backup auto-sync scheduler.

[INPUT]
app.services.memory.backup.backup_remote::RemoteBackupStrategy (POS: 本服务远程备份策略)
app.services.memory.backup.snapshot::capture_snapshot/apply_snapshot/encode_snapshot/decode_snapshot (POS: 本服务备份快照契约)

Runs one remote backup cycle (capture snapshot, upload, rotate) and remote restores for
WebDAV/S3. The APScheduler job in app.lifecycle.schedulers drives the periodic cycle; the
snapshot format is shared with the local volume backups.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import socket
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory import MemoryManager

from app.services.memory.backup.snapshot import (
    MemorySnapshot,
    SnapshotError,
    apply_snapshot,
    capture_snapshot,
    decode_snapshot,
    encode_snapshot,
)

if TYPE_CHECKING:
    from app.services.memory.backup.backup_remote import (
        RemoteBackupStrategy,
    )

logger = logging.getLogger(__name__)

_auto_backup_running = False

_MAX_UPLOAD_RETRIES = 3
_RETRY_BASE_DELAY_S = 2.0

# The remote name is only a selector on the storage provider; the download always lands under this fixed local name.
_DOWNLOAD_FILE_NAME = "backup.json.gz"


async def _upload_with_retry(
    strategy: "RemoteBackupStrategy",
    local_path: Path,
    remote_name: str,
) -> bool:
    """Upload with exponential backoff retry (max 3 attempts)."""
    for attempt in range(1, _MAX_UPLOAD_RETRIES + 1):
        try:
            ok = await strategy.upload(local_path, remote_name)
            if ok:
                return True
            if attempt < _MAX_UPLOAD_RETRIES:
                delay = _RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning(
                    "Upload attempt %d/%d failed, retrying in %.1fs",
                    attempt,
                    _MAX_UPLOAD_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
        except Exception as e:
            if attempt < _MAX_UPLOAD_RETRIES:
                delay = _RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
                logger.warning(
                    "Upload attempt %d/%d error: %s, retrying in %.1fs",
                    attempt,
                    _MAX_UPLOAD_RETRIES,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Upload failed after %d attempts: %s", _MAX_UPLOAD_RETRIES, e)
                return False
    return False


async def run_remote_backup(
    manager: MemoryManager,
    strategy: RemoteBackupStrategy,
    device_name: str = "",
    max_backups: int = 10,
) -> dict[str, object]:
    """Execute a single remote backup cycle.

    Steps:
    1. Capture a complete memory snapshot (fails instead of uploading a partial one)
    2. Compress and upload it to the remote
    3. Rotate old backups beyond max_backups (per device)

    Returns:
        Result dict with success, file_name, size_bytes, duration_ms
    """
    global _auto_backup_running
    if _auto_backup_running:
        return {"success": False, "error": "Backup already in progress"}

    _auto_backup_running = True
    start = datetime.now(UTC)

    try:
        snapshot = await capture_snapshot(manager)

        hostname = device_name or socket.gethostname() or "unknown"
        device_type = platform.system().lower() or "unknown"
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        backup_filename = f"myrm.{timestamp}.{hostname}.{device_type}.json.gz"

        with tempfile.TemporaryDirectory(prefix="myrm_remote_backup_") as temp_dir:
            local_path = Path(temp_dir) / _DOWNLOAD_FILE_NAME
            file_size = await asyncio.to_thread(_write_snapshot_file, local_path, snapshot)
            upload_ok = await _upload_with_retry(strategy, local_path, backup_filename)

        if not upload_ok:
            return {
                "success": False,
                "error": "Remote upload failed after retries",
                "duration_ms": _elapsed_ms(start),
            }

        if max_backups > 0:
            await _rotate_backups(strategy, hostname, device_type, max_backups)

        return {
            "success": True,
            "file_name": backup_filename,
            "size_bytes": file_size,
            "duration_ms": _elapsed_ms(start),
        }
    except SnapshotError as e:
        logger.warning("Remote backup aborted: %s", e)
        return {"success": False, "error": str(e), "duration_ms": _elapsed_ms(start)}
    except Exception as e:
        logger.exception("Remote backup failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "duration_ms": _elapsed_ms(start),
        }
    finally:
        _auto_backup_running = False


async def restore_from_remote(
    manager: MemoryManager,
    strategy: RemoteBackupStrategy,
    file_name: str,
) -> dict[str, object]:
    """Download a remote backup and merge it into the current memories.

    Restoring is non-destructive: entries the store already holds are skipped, nothing is
    deleted, so a restore on a fresh device equals a full restore.

    Returns:
        Result dict with success, restored_count, duration_ms
    """
    start = datetime.now(UTC)

    try:
        with tempfile.TemporaryDirectory(prefix="myrm_restore_") as temp_dir:
            local_path = Path(temp_dir) / _DOWNLOAD_FILE_NAME
            if not await strategy.download(file_name, local_path):
                return {
                    "success": False,
                    "error": f"Failed to download {file_name} from remote",
                    "duration_ms": _elapsed_ms(start),
                }
            snapshot = await asyncio.to_thread(_read_snapshot_file, local_path)

        counts = await apply_snapshot(manager, snapshot, replace=False)
        return {
            "success": True,
            "restored_count": sum(counts.values()),
            "duration_ms": _elapsed_ms(start),
        }
    except SnapshotError as e:
        logger.warning("Remote restore rejected: %s", e)
        return {"success": False, "error": str(e), "duration_ms": _elapsed_ms(start)}
    except Exception as e:
        logger.exception("Remote restore failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "duration_ms": _elapsed_ms(start),
        }


async def _rotate_backups(
    strategy: RemoteBackupStrategy,
    hostname: str,
    device_type: str,
    max_backups: int,
) -> None:
    """Delete old backups exceeding max_backups for this device."""
    try:
        all_files = await strategy.list_files()

        device_files = [f for f in all_files if hostname in f.file_name and device_type in f.file_name]

        if len(device_files) <= max_backups:
            return

        to_delete = device_files[max_backups:]
        for f in to_delete:
            await strategy.delete(f.file_name)
            logger.info("Rotated old backup: %s", f.file_name)
    except Exception as e:
        logger.warning("Backup rotation failed: %s", e)


def _write_snapshot_file(path: Path, snapshot: MemorySnapshot) -> int:
    return path.write_bytes(encode_snapshot(snapshot))


def _read_snapshot_file(path: Path) -> MemorySnapshot:
    return decode_snapshot(path.read_bytes())


def _elapsed_ms(start: datetime) -> float:
    return (datetime.now(UTC) - start).total_seconds() * 1000
