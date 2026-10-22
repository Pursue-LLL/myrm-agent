"""Shared steps for the export -> upload -> stage tests.

[INPUT]
- app.services.instance_archive: export, upload store and importer under test
- tests.services.instance_archive.conftest: source/target keys

[OUTPUT]
- export_archive / upload_archive / make_importer / stage_archive and two SQLite readers

[POS]
Test steps of the archive round trip: export a source instance, upload the package and stage it into a target instance.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.services.instance_archive import (
    ArchivePaths,
    ImportEnvironment,
    ImportReport,
    InstanceImporter,
    UploadStore,
)
from app.services.instance_archive.export_service import build_export
from tests.services.instance_archive.conftest import SOURCE_KEY, TARGET_KEY

PASSPHRASE = "correct horse battery"
CHUNK_BYTES = 32 * 1024


def export_archive(source: Path, dest: Path, *, passphrase: str | None = PASSPHRASE) -> Path:
    build_export(
        state_dir=source,
        dest=dest,
        user_id="user-a",
        app_version="1.0.0",
        deploy_mode="local",
        config_key=SOURCE_KEY,
        passphrase=passphrase,
    )
    return dest


def upload_archive(store: UploadStore, archive: Path) -> str:
    data = archive.read_bytes()
    session = store.create(len(data), CHUNK_BYTES)
    for index in reversed(range(session.chunk_count)):  # out of order on purpose
        store.write_chunk(session.session_id, index, data[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES])
    return session.session_id


def make_importer(target: Path, *, user_id: str = "user-a", target_key: bytes | None = TARGET_KEY, max_version: int = 10):
    paths = ArchivePaths(target)
    env = ImportEnvironment(paths=paths, user_id=user_id, max_schema_version=max_version, target_key=target_key)
    store = UploadStore(paths)
    return InstanceImporter(env, store), store, paths


def stage_archive(
    target: Path,
    archive: Path,
    *,
    user_id: str = "user-a",
    target_key: bytes | None = TARGET_KEY,
    passphrase: str | None = PASSPHRASE,
) -> tuple[ImportReport, InstanceImporter, UploadStore, str]:
    importer, store, _ = make_importer(target, user_id=user_id, target_key=target_key)
    session_id = upload_archive(store, archive)
    report = importer.stage(session_id, passphrase=passphrase, skip_secrets=False)
    return report, importer, store, session_id


def query_rows(db: Path, sql: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def read_config(db: Path, key: str) -> object:
    rows = query_rows(db, f"SELECT config_value FROM user_configs WHERE config_key = '{key}'")
    return json.loads(rows[0][0]) if rows else None  # type: ignore[arg-type]
