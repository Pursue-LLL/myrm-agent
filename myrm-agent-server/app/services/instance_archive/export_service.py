"""Instance export: stream a consistent, scrubbed state archive to disk.

[INPUT]
- app.services.instance_archive.policy::scan_state_dir (POS: what travels, and which carried paths could not be read)
- app.services.instance_archive.table_policy (POS: data.db row policy)
- app.services.instance_archive.checkpoint_scrub::live_checkpoint_scrubber (POS: removes web incognito threads from the checkpoints.db copy)
- app.services.instance_archive.incognito_workspaces::without_incognito_workspaces (POS: drops the workspace files of web incognito chats from the scan)
- app.services.instance_archive.incognito_uploads::without_incognito_uploads (POS: drops the uploads bound to incognito chats from the scan)
- app.services.instance_archive.envelope::seal_key (POS: passphrase-wrapped config key)
- myrm_agent_harness.infra.state_archive::ArchiveWriter (POS: archive primitive)

[OUTPUT]
- build_export: write one archive and return its facts, including the carried paths it could not include (their count is also recorded in the manifest)
- DataDbScrubber: the ``prepare`` callback applied to the archived data.db copy; the checkpoints.db copy gets ``live_checkpoint_scrubber``
- ExportProgress / ExportResult / ExportError / ExportCancelledError

[POS]
Synchronous export pipeline meant to run in a worker thread. Memory use is
constant (files stream into the zip); the live data.db is snapshotted with
VACUUM INTO so deleted-row residue never reaches the archive, then scrubbed.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.infra.state_archive import ArchiveWriter, SkippedEntry, ensure_free_space
from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError

from app.services.instance_archive.checkpoint_scrub import CHECKPOINTS_DB_NAME, live_checkpoint_scrubber
from app.services.instance_archive.envelope import seal_key
from app.services.instance_archive.incognito_uploads import without_incognito_uploads
from app.services.instance_archive.incognito_workspaces import without_incognito_workspaces
from app.services.instance_archive.policy import MAIN_DB_NAME, PathCategory, StateScan, scan_state_dir
from app.services.instance_archive.table_policy import (
    HOST_BOUND_TABLES,
    SECRET_TABLES,
    ConfigRowPolicy,
    config_needs_reentry,
    config_row_policy,
    delete_all_rows,
    live_surviving_chat_ids,
    live_web_incognito_chat_ids,
    scrub_sensitive_surface,
    table_names,
)

logger = logging.getLogger(__name__)

_PRODUCER = {"name": "myrm-agent-server"}
_LOGGED_UNREADABLE = 5


class ExportError(RuntimeError):
    """The archive could not be produced faithfully."""


class ExportCancelledError(RuntimeError):
    """The user cancelled the export."""


@dataclass(frozen=True, slots=True)
class ExportProgress:
    files_done: int
    files_total: int
    bytes_done: int
    bytes_total: int


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    size_bytes: int
    entry_count: int
    reentry: tuple[str, ...]
    config_key_carried: bool
    unreadable: tuple[str, ...]  # carried by policy, present on disk, yet not in the archive


class DataDbScrubber:
    """``prepare`` callback: keeps only what is safe and meaningful on another host."""

    def __init__(self, *, source_key: bytes | None, carry_sensitive: bool) -> None:
        self._source_key = source_key
        self._carry_sensitive = carry_sensitive and source_key is not None
        self.schema_version: int | None = None
        self.reentry: list[str] = []
        self.carried: list[str] = []

    def __call__(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA secure_delete = ON")
            existing = table_names(conn)
            if "_schema_migrations" in existing:
                row = conn.execute("SELECT MAX(version) FROM _schema_migrations").fetchone()
                self.schema_version = None if row[0] is None else int(row[0])
            scrub_sensitive_surface(conn)
            dropped = delete_all_rows(conn, HOST_BOUND_TABLES | SECRET_TABLES)
            self.reentry.extend(f"table:{name}" for name in sorted(SECRET_TABLES) if name in dropped)
            if "user_configs" in existing:
                self._scrub_user_configs(conn)
            conn.commit()
        finally:
            conn.close()

    def _scrub_user_configs(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT config_key, config_value, is_encrypted FROM user_configs").fetchall()
        for key, value, is_encrypted in rows:
            policy = config_row_policy(key)
            if policy is ConfigRowPolicy.DATA:
                continue
            if policy is ConfigRowPolicy.PORTABLE_SECRET and self._carry_sensitive and self._opens(value, is_encrypted):
                self.carried.append(key)
                continue
            conn.execute("DELETE FROM user_configs WHERE config_key = ?", (key,))
            if config_needs_reentry(key):
                self.reentry.append(f"config:{key}")

    def _opens(self, raw_value: str, is_encrypted: object) -> bool:
        """Only rows that are real ciphertext under the source key may travel."""
        if not is_encrypted or self._source_key is None:
            return False
        try:
            ciphertext = json.loads(raw_value)
            if not isinstance(ciphertext, str):
                return False
            ConfigCrypto.decrypt_value(ciphertext, self._source_key)
        except (ValueError, DecryptionError):
            return False
        return True


def build_export(
    *,
    state_dir: Path,
    dest: Path,
    user_id: str,
    app_version: str,
    deploy_mode: str,
    config_key: bytes | None,
    passphrase: str | None,
    progress: Callable[[ExportProgress], None] | None = None,
    cancel: threading.Event | None = None,
) -> ExportResult:
    """Write the archive to ``dest``. ``passphrase`` (local mode only) lets sensitive config travel."""
    scan = scan_state_dir(state_dir)
    # Read after the scan: every workspace it listed belongs to a chat that already had its row.
    scan = without_incognito_workspaces(scan, _live_incognito_chat_ids(state_dir))
    scan = without_incognito_uploads(scan, _live_surviving_chat_ids(state_dir))
    sources, excluded = scan.sources, scan.excluded
    bytes_total = sum(s.size for s in sources)
    ensure_free_space(dest.parent, bytes_total)
    envelope = seal_key(config_key, passphrase) if passphrase and config_key else None
    scrubber = DataDbScrubber(source_key=config_key, carry_sensitive=envelope is not None)
    checkpoint_scrubber = live_checkpoint_scrubber(state_dir / MAIN_DB_NAME)
    metadata: dict[str, object] = {
        "app_version": app_version,
        "deploy_mode": deploy_mode,
        "source_user_id": user_id,
        "excluded": dict(Counter(e.category.value for e in excluded)),
    }
    files_done = bytes_done = 0
    with ArchiveWriter(dest, producer=_PRODUCER, metadata=metadata, work_dir=dest.parent) as writer:
        for source in sources:
            if cancel is not None and cancel.is_set():
                raise ExportCancelledError("Export cancelled")
            if source.rel == MAIN_DB_NAME:
                writer.add_sqlite(source.path, source.rel, prepare=scrubber)
            elif source.rel == CHECKPOINTS_DB_NAME:
                writer.add_sqlite(source.path, source.rel, prepare=checkpoint_scrubber)
            elif source.is_sqlite:
                writer.add_sqlite(source.path, source.rel)
            else:
                writer.add_file(source.path, source.rel)
            files_done += 1
            bytes_done += source.size
            if progress is not None:
                progress(ExportProgress(files_done, len(sources), bytes_done, bytes_total))
        if any(item.path == MAIN_DB_NAME for item in writer.skipped) or scrubber.schema_version is None:
            raise ExportError("The main database could not be captured")
        reentry = (
            *scrubber.reentry,
            *(f"path:{e.rel}" for e in excluded if e.category is PathCategory.SECRET),
        )
        writer.set_metadata("schema_version", scrubber.schema_version)
        writer.set_metadata("reentry", list(reentry))
        writer.set_metadata("config_envelope", envelope)
        unreadable = _left_out(state_dir, scan, writer.skipped)
        writer.set_metadata("unreadable_count", len(unreadable))
        manifest = writer.finalize()
    if unreadable:
        logger.warning(
            "[InstanceArchive] %d item(s) could not be read and are not in the archive, first: %s",
            len(unreadable),
            ", ".join(unreadable[:_LOGGED_UNREADABLE]),
        )
    return ExportResult(dest, dest.stat().st_size, len(manifest.entries), reentry, envelope is not None, unreadable)


def _live_incognito_chat_ids(state_dir: Path) -> list[str]:
    """The web incognito chats right now. A database that cannot be read fails the export: every workspace would travel."""
    try:
        return live_web_incognito_chat_ids(state_dir / MAIN_DB_NAME)
    except sqlite3.Error as exc:
        raise ExportError("The main database could not be captured") from exc


def _live_surviving_chat_ids(state_dir: Path) -> set[str]:
    """The chats an archive keeps. A database that cannot be read fails the export: every bound upload would travel."""
    try:
        return live_surviving_chat_ids(state_dir / MAIN_DB_NAME)
    except sqlite3.Error as exc:
        raise ExportError("The main database could not be captured") from exc


def _left_out(state_dir: Path, scan: StateScan, skipped: Iterable[SkippedEntry]) -> tuple[str, ...]:
    """Paths that exist but are missing from the archive. A file removed while the export ran is no loss."""
    refused = (item.path for item in skipped if not _removed(state_dir / item.path))
    return tuple(sorted({*scan.unreadable, *refused}))


def _removed(path: Path) -> bool:
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return False
    return False
