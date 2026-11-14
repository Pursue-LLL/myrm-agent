"""Browser Doctor — stale browser profile directory cleanup.

Playwright gives every Chromium it launches a throw-away profile directory in the temp
directory and deletes it when the browser is closed. A browser that goes down with its
driver (crash, SIGKILL, power loss) leaves the directory behind, and nothing else removes
it. This module prunes such directories once they are old enough and no running process
uses them, dry-run by default.

[INPUT]
- psutil (optional, process table: which directories running browsers use as ``--user-data-dir``)
- .orphans::extract_user_data_dir (POS: ``--user-data-dir`` value of a command line)

[OUTPUT]
- cleanup_stale_browser_profiles: dry-run-first profile prune returning a ProfileCleanupResult
- ProfileCleanupResult / ProfileFailure: typed shape of the prune summary

[POS]
Stale browser profile cleanup. A browser keeps its profile for as long as it runs, so age alone
proves nothing and liveness comes from the process table: every directory that a running process
passes as ``--user-data-dir`` is left alone, in the preview and in the prune alike, and an
unreadable process table protects everything. Only real directories of the current user that sit
directly in the temp directory and carry Playwright's Chromium profile prefix are ever touched.
The walk is synchronous and offloaded via asyncio.to_thread by callers (doctor orchestrator,
server health endpoints).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import TypedDict

from .orphans import extract_user_data_dir

logger = logging.getLogger(__name__)

# Playwright names each profile ``<temp dir>/playwright_chromiumdev_profile-<random suffix>``.
_PROFILE_PREFIX = "playwright_chromiumdev_profile-"


class ProfileFailure(TypedDict):
    """A profile directory that could not be removed."""

    path: str
    reason: str


class ProfileCleanupResult(TypedDict):
    """Summary of one profile prune pass."""

    pruned: int
    reclaimed_bytes: int
    dry_run: bool
    failed: list[ProfileFailure]


def _is_stale_own_profile(entry: os.DirEntry[str], modified_before: float) -> bool:
    """Whether ``entry`` is a real (not symlinked) directory of this user that last changed by ``modified_before``."""
    try:
        if not entry.is_dir(follow_symlinks=False):
            return False
        stat = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    # Windows has no user ids to compare.
    owned = not hasattr(os, "getuid") or stat.st_uid == os.getuid()
    return owned and stat.st_mtime <= modified_before


def _stale_profile_directories(modified_before: float) -> list[Path]:
    """This user's profile directories in the temp directory that last changed by ``modified_before``."""
    try:
        with os.scandir(tempfile.gettempdir()) as entries:
            return [
                Path(entry.path)
                for entry in entries
                if entry.name.startswith(_PROFILE_PREFIX) and _is_stale_own_profile(entry, modified_before)
            ]
    except OSError as exc:
        logger.debug("Scan of the temp directory for browser profiles skipped: %s", exc)
        return []


def _in_use_profile_names() -> frozenset[str] | None:
    """Directory names that running processes pass as ``--user-data-dir``.

    Returns ``None`` when the process table cannot be read; callers must then treat every
    profile as in use, because "nothing runs" would be a guess. Names are compared instead of
    paths because a path has several spellings (macOS reaches the temp directory through both
    ``/var`` and ``/private/var``) while the random suffix Playwright appends is unique to one
    launch, so a clash can only keep a directory and never remove one.
    """
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not available, cannot tell whether a browser still uses its profile")
        return None

    names: set[str] = set()
    try:
        for proc in psutil.process_iter():
            try:
                user_data_dir = extract_user_data_dir(proc.cmdline())
            except (psutil.Error, OSError, SystemError):  # SystemError: psutil on macOS
                continue  # gone, or another user's process, which cannot hold this user's profile
            if user_data_dir:
                names.add(Path(user_data_dir).name)
    except Exception as exc:
        logger.warning("Failed to read the process table for profile liveness: %s", exc)
        return None
    return frozenset(names)


def _directory_bytes(directory: Path) -> int:
    """Total size of the files below ``directory``; an entry that cannot be read counts as zero."""
    total = 0
    for root, _subdirectories, files in os.walk(directory):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def cleanup_stale_browser_profiles(
    max_age_hours: float = 24.0,
    *,
    dry_run: bool = True,
) -> ProfileCleanupResult:
    """Prune throw-away Chromium profile directories older than ``max_age_hours`` that no process uses.

    Profiles of any Playwright Chromium qualify, not only those the toolkit launched; one is
    skipped while a running process passes it as ``--user-data-dir`` (dry-run included), so the
    preview matches the prune.

    Args:
        max_age_hours: Minimum time in hours since the directory last changed before it is eligible.
        dry_run: If True, only reports what would be removed.

    Returns:
        Summary of the pruned (dry-run: prunable) directories and the bytes they hold.
    """
    candidates = _stale_profile_directories(modified_before=time.time() - max_age_hours * 3600.0)
    # Only a machine with leftover profiles pays for the process-table walk.
    in_use = _in_use_profile_names() if candidates else frozenset[str]()

    pruned = 0
    reclaimed_bytes = 0
    failed: list[ProfileFailure] = []
    for profile in candidates:
        if in_use is None or profile.name in in_use:
            logger.debug("Skipping browser profile %s: a browser still uses it or liveness is unknown", profile)
            continue

        size = _directory_bytes(profile)
        if not dry_run:
            try:
                shutil.rmtree(profile)
            except FileNotFoundError:
                continue  # removed concurrently by the browser's own cleanup or an OS temp cleaner
            except OSError as exc:
                logger.warning("Failed to remove stale browser profile %s: %s", profile, exc)
                failed.append({"path": str(profile), "reason": str(exc)})
                continue
            logger.info("Pruned stale browser profile: %s", profile)

        pruned += 1
        reclaimed_bytes += size

    return {"pruned": pruned, "reclaimed_bytes": reclaimed_bytes, "dry_run": dry_run, "failed": failed}
