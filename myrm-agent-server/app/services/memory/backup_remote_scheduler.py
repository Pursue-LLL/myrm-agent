"""Remote backup auto-sync scheduler.

Manages periodic automatic backup to configured remote storage (WebDAV/S3).
Integrates with the existing APScheduler lifecycle and VolumeBackupStrategy.
"""

from __future__ import annotations

import logging
import platform
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.memory.backup_remote import (
        RemoteBackupStrategy,
    )

logger = logging.getLogger(__name__)

_auto_backup_running = False

_MAX_UPLOAD_RETRIES = 3
_RETRY_BASE_DELAY_S = 2.0


async def _upload_with_retry(
    strategy: "RemoteBackupStrategy",
    local_path: Path,
    remote_name: str,
) -> bool:
    """Upload with exponential backoff retry (max 3 attempts)."""
    import asyncio

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
    strategy: RemoteBackupStrategy,
    backup_root: Path | None = None,
    device_name: str = "",
    max_backups: int = 10,
) -> dict[str, object]:
    """Execute a single remote backup cycle.

    Steps:
    1. Create local backup via VolumeBackupStrategy
    2. Compress and upload to remote
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
        from app.services.memory.backup import VolumeBackupStrategy as LocalStrategy

        local_strategy = LocalStrategy(backup_root=backup_root)

        hostname = device_name or socket.gethostname() or "unknown"
        device_type = platform.system().lower() or "unknown"
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        backup_filename = f"myrm.{timestamp}.{hostname}.{device_type}.json.gz"

        from app.services.memory.backup_remote_utils import (
            create_exportable_backup,
        )

        local_backup_path = await create_exportable_backup(local_strategy, backup_filename)

        if local_backup_path is None:
            return {
                "success": False,
                "error": "Failed to create local backup for remote upload",
                "duration_ms": _elapsed_ms(start),
            }

        file_size = local_backup_path.stat().st_size if local_backup_path.exists() else 0

        upload_ok = await _upload_with_retry(strategy, local_backup_path, backup_filename)
        local_backup_path.unlink(missing_ok=True)

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
    strategy: RemoteBackupStrategy,
    file_name: str,
    backup_root: Path | None = None,
) -> dict[str, object]:
    """Download and restore a remote backup.

    Steps:
    1. Download from remote to temp location
    2. Restore via VolumeBackupStrategy

    Returns:
        Result dict with success, restored_count, duration_ms
    """
    import tempfile

    start = datetime.now(UTC)

    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="myrm_restore_"))
        local_path = temp_dir / file_name

        download_ok = await strategy.download(file_name, local_path)
        if not download_ok:
            return {
                "success": False,
                "error": f"Failed to download {file_name} from remote",
                "duration_ms": _elapsed_ms(start),
            }

        from app.services.memory.backup_remote_utils import (
            restore_from_exportable_backup,
        )

        result = await restore_from_exportable_backup(local_path, backup_root)

        local_path.unlink(missing_ok=True)
        temp_dir.rmdir()

        return {
            "success": result.get("success", False),
            "restored_count": result.get("restored_count", 0),
            "duration_ms": _elapsed_ms(start),
            "error": result.get("error"),
        }
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


def _elapsed_ms(start: datetime) -> float:
    return (datetime.now(UTC) - start).total_seconds() * 1000
