"""Instance import: verify, stage, report, and queue the promotion for the next boot.

[INPUT]
- app.services.instance_archive.uploads::UploadStore (POS: archive bytes)
- app.services.instance_archive.stage_db::prepare_staged_db (POS: data.db scrub / graft)
- app.services.instance_archive.policy (POS: import-side path gate)
- myrm_agent_harness.infra.state_archive (POS: verified extraction)

[OUTPUT]
- ImportEnvironment: identity, schema-version gate and key facts the import decisions depend on
- InstanceImporter.stage / confirm / cancel
- ImportRejectedError: stable machine-readable rejection

[POS]
Everything that can be checked while the app is running happens here: archive
integrity, version gate, path allow-list (a hostile archive cannot overwrite a
key, a password hash or the working directory), database scrub/graft and the
user-facing report. ``confirm`` only writes the pending marker; the swap itself
runs before the next boot opens any database (see promotion_hook).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from itertools import chain
from pathlib import Path

from myrm_agent_harness.infra.state_archive import (
    ArchiveEntry,
    ArchiveVerificationError,
    InsufficientSpaceError,
    ensure_free_space,
    extract_payload,
    is_sqlite_file,
    read_manifest,
)

from app.services.instance_archive.envelope import EnvelopeError, unseal_key
from app.services.instance_archive.models import ArchivePaths, ImportReport, Operation, PendingPromotion
from app.services.instance_archive.policy import MAIN_DB_NAME, classify_path, is_importable_entry
from app.services.instance_archive.promotion_hook import prepare_pending_for
from app.services.instance_archive.stage_db import StageContext, StagedDbResult, StageRejected, prepare_staged_db
from app.services.instance_archive.uploads import UploadStore

_SCRIPT_SUFFIXES = frozenset({".py", ".sh", ".bash", ".js", ".mjs", ".ts"})
_SIDECARS = ("-wal", "-shm", "-journal")
_REENTRY_KINDS = ("config:", "table:", "path:")
# An instance holds a few dozen credential rows at most (about 30 `*Credentials` keys, 5 portable keys, 2 secret tables);
# the archive is untrusted, so the report keeps a bounded, well-formed set with ample headroom.
_MAX_REENTRY_ITEMS = 128
_MAX_REENTRY_LENGTH = 512
# The archive is untrusted: the number of unreadable items shown to the user is clamped to a plausible size.
_MAX_UNREADABLE = 1_000_000


class ImportRejectedError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ImportEnvironment:
    paths: ArchivePaths
    user_id: str
    max_schema_version: int
    target_key: bytes | None  # None on targets that must not hold imported secrets (sandbox)


def _count_files(root: Path, suffixes: frozenset[str] | None) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _, _, names in os.walk(root) for name in names if suffixes is None or Path(name).suffix.lower() in suffixes)


def _swap_entries(state_dir: Path, staged_dir: Path) -> tuple[str, ...]:
    """Top-level names to swap: everything staged plus every carried-class name living in the target."""
    names = {entry.name for entry in staged_dir.iterdir()}
    names |= {e.name for e in os.scandir(state_dir) if classify_path((e.name,)).include}
    for name in list(names):
        if is_sqlite_file(staged_dir / name) or is_sqlite_file(state_dir / name):
            names.update(f"{name}{suffix}" for suffix in _SIDECARS)
    return tuple(sorted(names))


class InstanceImporter:
    def __init__(self, env: ImportEnvironment, store: UploadStore) -> None:
        self._env = env
        self._store = store

    def stage(self, session_id: str, *, passphrase: str | None, skip_secrets: bool) -> ImportReport:
        session = self._store.get(session_id)
        if session.state != "uploading" or not session.complete:
            raise ImportRejectedError("upload_incomplete", "The upload is not complete")
        archive = self._store.archive_path(session_id)
        try:
            manifest = read_manifest(archive)
        except ArchiveVerificationError as exc:
            raise ImportRejectedError("invalid_archive", str(exc)) from exc
        metadata = manifest.metadata
        source_key = self._open_envelope(metadata.get("config_envelope"), passphrase, skip_secrets)

        staging = self._env.paths.staging / session_id
        shutil.rmtree(staging, ignore_errors=True)
        try:
            ensure_free_space(self._env.paths.staging.parent, manifest.total_bytes)
            written = extract_payload(archive, manifest, staging, select=_importable)
            if not any(e.path == MAIN_DB_NAME for e in written):
                raise ImportRejectedError("no_main_db", "The archive does not contain the main database")
            staged = self._prepare_db(staging / MAIN_DB_NAME, metadata.get("source_user_id"), source_key)
        except ImportRejectedError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        except StageRejected as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise ImportRejectedError(exc.code, str(exc)) from exc
        except InsufficientSpaceError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise ImportRejectedError("insufficient_space", "Not enough free disk space to verify this archive") from exc
        except ArchiveVerificationError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise ImportRejectedError("invalid_archive", str(exc)) from exc
        except sqlite3.Error as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise ImportRejectedError("stage_failed", "The archived database could not be prepared") from exc
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        report = self._report(session_id, manifest.created_at, staged, metadata.get("reentry"), metadata.get("unreadable_count"))
        session.state = "staged"
        session.report = report.to_dict()
        self._store.save(session)
        archive.unlink(missing_ok=True)
        return report

    def confirm(self, session_id: str, *, acknowledge_executables: bool) -> PendingPromotion:
        paths = self._env.paths
        session = self._store.get(session_id)
        if session.state != "staged" or session.report is None:
            raise ImportRejectedError("not_staged", "The archive has not been verified")
        if paths.pending.exists():
            raise ImportRejectedError("operation_pending", "Another restore is already waiting for a restart")
        executable = session.report.get("executable")
        if isinstance(executable, dict) and any(executable.values()) and not acknowledge_executables:
            raise ImportRejectedError("acknowledgement_required", "Executable content must be acknowledged")
        staging = paths.staging / session_id
        counts, reentry = session.report.get("counts"), session.report.get("reentry")
        pending = prepare_pending_for(
            paths,
            operation=Operation.IMPORT,
            staging=staging,
            aside=paths.aside / session_id,
            entries=_swap_entries(paths.state_dir, staging),
            summary={k: v for k, v in (counts.items() if isinstance(counts, dict) else []) if isinstance(v, int)},
            reentry=tuple(str(r) for r in reentry) if isinstance(reentry, list) else (),
        )
        session.state = "confirmed"
        self._store.save(session)
        return pending

    def cancel(self, session_id: str) -> None:
        session = self._store.get(session_id)
        if session.state == "confirmed":
            self._env.paths.pending.unlink(missing_ok=True)
        self._store.discard(session_id)

    def _open_envelope(self, envelope: object, passphrase: str | None, skip_secrets: bool) -> bytes | None:
        if not isinstance(envelope, dict) or skip_secrets or self._env.target_key is None:
            return None
        if not passphrase:
            raise ImportRejectedError("passphrase_required", "This archive is protected by a passphrase")
        try:
            return unseal_key(envelope, passphrase)
        except EnvelopeError as exc:
            raise ImportRejectedError("wrong_passphrase", "The passphrase is incorrect") from exc

    def _prepare_db(self, staged_db: Path, source_user_id: object, source_key: bytes | None) -> StagedDbResult:
        live_db = self._env.paths.state_dir / MAIN_DB_NAME
        return prepare_staged_db(
            staged_db,
            StageContext(
                live_db=live_db,
                source_user_id=source_user_id if isinstance(source_user_id, str) else None,
                target_user_id=self._env.user_id,
                max_schema_version=self._env.max_schema_version,
                source_key=source_key,
                target_key=self._env.target_key,
            ),
        )

    def _report(
        self, session_id: str, created_at: str, staged: StagedDbResult, declared_reentry: object, declared_unreadable: object
    ) -> ImportReport:
        root = self._env.paths.staging / session_id
        skills_dir = root / "skills"
        counts = dict(staged.counts)
        counts["skills"] = sum(1 for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else 0
        counts["wiki_pages"] = _count_files(root / "wiki", frozenset({".md"}))
        executable = {**staged.executable, "skill_scripts": _count_files(skills_dir, _SCRIPT_SUFFIXES)}
        return ImportReport(
            session_id=session_id,
            created_at=_backup_time(created_at),
            counts=counts,
            current_counts=dict(staged.current_counts),
            executable=executable,
            reentry=_bounded_reentry(declared_reentry, staged.reentry),
            paused_jobs=staged.paused_jobs,
            missing_paths=staged.missing_paths,
            unreadable_count=_bounded_count(declared_unreadable),
            identity_dropped=staged.identity_dropped,
            config_key_carried=staged.config_key_carried,
        )


def _bounded_reentry(declared: object, staged: Iterable[str]) -> tuple[str, ...]:
    """Credentials to enter again: what the archive declares plus what staging found, well-formed and bounded."""
    candidates = chain(declared if isinstance(declared, list) else (), staged)
    kept = {r for r in candidates if isinstance(r, str) and len(r) <= _MAX_REENTRY_LENGTH and r.startswith(_REENTRY_KINDS)}
    return tuple(sorted(kept)[:_MAX_REENTRY_ITEMS])


def _bounded_count(declared: object) -> int:
    """How many items the export declares it could not read: a non-negative integer, anything else counts as none."""
    if type(declared) is not int or declared < 0:
        return 0
    return min(declared, _MAX_UNREADABLE)


def _backup_time(raw: str) -> str:
    """The manifest timestamp in canonical form; the archive is untrusted, so anything else is dropped."""
    try:
        return datetime.fromisoformat(raw).isoformat()
    except ValueError:
        return ""


def _importable(entry: ArchiveEntry) -> bool:
    return is_importable_entry(entry.path)
