"""A config's audit history never outlives the row it describes: keys that do not travel as plain data take their history along.

[INPUT]
app.services.instance_archive.export_service::DataDbScrubber/build_export
app.services.instance_archive.stage_db::prepare_staged_db
app.services.instance_archive.table_policy::scrub_sensitive_surface

[OUTPUT]
That no archive carries (and no import keeps) the plaintext values a secret config had before it was encrypted, and that the
remote backup settings travel like the other portable secrets: only under the passphrase, re-keyed on import.

[POS]
The two shared scrub paths (export and import staging) over a database with a real audit table, plus the whole round trip.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError

from app.services.instance_archive import ArchivePaths
from app.services.instance_archive.export_service import DataDbScrubber
from app.services.instance_archive.stage_db import StageContext, prepare_staged_db
from tests.services.instance_archive.archive_flow import export_archive, query_rows, read_config, stage_archive
from tests.services.instance_archive.conftest import SOURCE_KEY, TARGET_KEY, create_instance_db, put_config, seal_config

_AUDIT_TABLE = """
CREATE TABLE config_audit_logs (
    id VARCHAR(255) PRIMARY KEY, config_key VARCHAR(100) NOT NULL, previous_value JSON, new_value JSON NOT NULL,
    version VARCHAR(50) NOT NULL, device_id VARCHAR(100) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

# What the history of each kind of row holds in plaintext when it was written before the key was encrypted.
_HISTORY: dict[str, dict[str, object]] = {
    "providers": {"openai": "sk-history-provider"},
    "backupSync": {"provider": "webdav", "webdav": {"password": "dav-history-secret"}},
    "telegramCredentials": {"bot": "tg-history-secret"},
    "wikiSourceSync": {"folder": "/Users/me/private-notes"},
    "channelInstances": {"telegram": ["history-channel"]},
    "onboarding": {"done": True},
}
_KEPT_HISTORY = [("onboarding",)]
_SECRETS = (b"sk-history-provider", b"dav-history-secret", b"tg-history-secret", b"/Users/me/private-notes")


def _add_history(db: Path) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute(_AUDIT_TABLE)
        for key, value in _HISTORY.items():
            conn.execute(
                "INSERT INTO config_audit_logs (id, config_key, previous_value, new_value, version, device_id) "
                "VALUES (?, ?, NULL, ?, '1', 'device')",
                (f"history-{key}", key, json.dumps(value)),
            )
        conn.commit()
    finally:
        conn.close()


def _export(db: Path) -> None:
    DataDbScrubber(source_key=SOURCE_KEY, carry_sensitive=True)(db)


def _stage(db: Path) -> None:
    ctx = StageContext(
        live_db=None, source_user_id="u", target_user_id="u", max_schema_version=10**6, source_key=None, target_key=None
    )
    prepare_staged_db(db, ctx)


@pytest.fixture(params=[_export, _stage], ids=["export", "import-staging"])
def scrubbed(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    db = tmp_path / "data.db"
    create_instance_db(db).close()
    _add_history(db)
    scrub: Callable[[Path], None] = request.param
    scrub(db)
    return db


def test_the_history_of_a_row_that_does_not_travel_as_plain_data_is_dropped(scrubbed: Path) -> None:
    assert query_rows(scrubbed, "SELECT config_key FROM config_audit_logs") == _KEPT_HISTORY


def test_an_export_carries_no_plaintext_history_of_a_secret_even_in_freed_pages(tmp_path: Path) -> None:
    db = tmp_path / "data.db"
    create_instance_db(db).close()
    _add_history(db)

    _export(db)

    raw = db.read_bytes()
    assert [secret for secret in _SECRETS if secret in raw] == []


def test_a_database_without_an_audit_table_is_scrubbed_without_creating_one(tmp_path: Path) -> None:
    db = tmp_path / "data.db"
    create_instance_db(db).close()

    _export(db)

    assert query_rows(db, "SELECT name FROM sqlite_master WHERE name = 'config_audit_logs'") == []


def _source_with_remote_backup(source_state: Path) -> None:
    conn = sqlite3.connect(source_state / "data.db")
    try:
        put_config(
            conn,
            "backupSync",
            seal_config({"provider": "webdav", "webdav": {"password": "dav-live-secret"}}, SOURCE_KEY),
            encrypted=True,
        )
        conn.commit()
    finally:
        conn.close()
    _add_history(source_state / "data.db")


def _extract(archive: Path, extracted: Path) -> tuple[Path, bytes, dict[str, object]]:
    with zipfile.ZipFile(archive) as zf:
        extracted.write_bytes(zf.read("payload/data.db"))
        blob = b"".join(zf.read(name) for name in zf.namelist())
        metadata = json.loads(zf.read("manifest.json"))["metadata"]
    return extracted, blob, metadata


def test_the_remote_backup_settings_travel_only_under_the_passphrase(source_state: Path, tmp_path: Path) -> None:
    _source_with_remote_backup(source_state)

    with_passphrase = _extract(export_archive(source_state, tmp_path / "with.zip"), tmp_path / "with.db")
    without = _extract(export_archive(source_state, tmp_path / "without.zip", passphrase=None), tmp_path / "without.db")

    extracted, blob, _ = with_passphrase
    carried = read_config(extracted, "backupSync")
    assert isinstance(carried, str)
    assert ConfigCrypto.decrypt_value(carried, SOURCE_KEY)["webdav"] == {"password": "dav-live-secret"}  # type: ignore[index]
    assert [secret for secret in (*_SECRETS, b"dav-live-secret") if secret in blob] == []
    assert query_rows(extracted, "SELECT config_key FROM config_audit_logs") == _KEPT_HISTORY

    extracted, blob, metadata = without
    assert read_config(extracted, "backupSync") is None
    assert b"dav-live-secret" not in blob
    assert "config:backupSync" in metadata["reentry"]  # type: ignore[operator]


def test_an_imported_remote_backup_setting_is_re_keyed_to_the_target_and_brings_no_history(
    source_state: Path, target_state: Path, tmp_path: Path
) -> None:
    _source_with_remote_backup(source_state)

    _, _, _, session_id = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))
    staged = ArchivePaths(target_state).staging / session_id / "data.db"

    imported = read_config(staged, "backupSync")
    assert isinstance(imported, str)
    assert ConfigCrypto.decrypt_value(imported, TARGET_KEY)["provider"] == "webdav"  # type: ignore[index]
    with pytest.raises(DecryptionError):
        ConfigCrypto.decrypt_value(imported, SOURCE_KEY)
    assert query_rows(staged, "SELECT config_key FROM config_audit_logs") == _KEPT_HISTORY
