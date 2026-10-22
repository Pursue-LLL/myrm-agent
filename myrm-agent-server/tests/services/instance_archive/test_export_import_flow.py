"""End-to-end export -> upload -> stage -> confirm -> pre-boot promotion -> rollback."""

from __future__ import annotations

import base64
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from myrm_agent_harness.infra.state_archive import ArchiveWriter
from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError
from qdrant_client import QdrantClient

from app.services.instance_archive import (
    ArchivePaths,
    ImportRejectedError,
    OutcomeStatus,
    acknowledge_outcome,
    prepare_rollback,
    read_outcome,
    run_pending_promotion,
)
from app.services.instance_archive.export_service import ExportCancelledError, build_export
from tests.services.instance_archive.archive_flow import (
    PASSPHRASE,
    export_archive,
    make_importer,
    query_rows,
    read_config,
    stage_archive,
    upload_archive,
)
from tests.services.instance_archive.conftest import (
    MEMORY_CONTENTS,
    SOURCE_KEY,
    TARGET_KEY,
    create_instance_db,
    read_memory_contents,
)


def test_export_carries_no_plaintext_secret_and_leaves_machine_state_behind(source_state: Path, tmp_path: Path) -> None:
    archive = export_archive(source_state, tmp_path / "out.zip")

    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        blob = b"".join(zf.read(n) for n in names)
        manifest = json.loads(zf.read("manifest.json"))
    assert "payload/wiki/page.md" in names
    assert "payload/harness/workspace/proj/token-notes.txt" in names
    assert not [
        n for n in names if any(x in n for x in (".encryption_key", "webui/", "node_modules", "whatsapp_auth", "session_vault"))
    ]
    for secret in (
        b"RESIDUE-SECRET-MARKER",  # deleted row must not survive in free pages
        b"sk-source-provider",
        b"tg-secret",
        b"source-secret",
        b"source-agent-secret",
        b"fp-123",
        b"sk-whitelisted",
        b"SOURCE-MASTER-KEY",
        base64.b64encode(SOURCE_KEY),
    ):
        assert secret not in blob, secret

    metadata = manifest["metadata"]
    assert metadata["config_envelope"] is not None
    assert metadata["source_user_id"] == "user-a"
    assert "config:telegramCredentials" in metadata["reentry"]
    assert "table:agent_secrets" in metadata["reentry"]
    assert {"path:whatsapp_auth", "path:session_vault"} <= set(metadata["reentry"])  # sign-ins the user must redo
    assert not [r for r in metadata["reentry"] if r in ("path:.encryption_key", "path:vault.key")]  # machine keys


def test_export_without_passphrase_drops_every_sensitive_config(source_state: Path, tmp_path: Path) -> None:
    archive = export_archive(source_state, tmp_path / "out.zip", passphrase=None)
    extracted = tmp_path / "data.db"
    with zipfile.ZipFile(archive) as zf:
        extracted.write_bytes(zf.read("payload/data.db"))
        metadata = json.loads(zf.read("manifest.json"))["metadata"]

    assert metadata["config_envelope"] is None
    assert read_config(extracted, "providers") is None
    assert read_config(extracted, "mcpServers") is None
    assert read_config(extracted, "onboarding") == {"done": True}
    assert "config:providers" in metadata["reentry"]


def test_export_cancel_leaves_no_partial_file(source_state: Path, tmp_path: Path) -> None:
    import threading

    cancel = threading.Event()
    cancel.set()
    dest = tmp_path / "out.zip"
    with pytest.raises(ExportCancelledError):
        build_export(
            state_dir=source_state,
            dest=dest,
            user_id="user-a",
            app_version="1.0.0",
            deploy_mode="local",
            config_key=None,
            passphrase=None,
            cancel=cancel,
        )
    assert not dest.exists()
    assert not list(tmp_path.glob("*.partial"))


def test_passphrase_is_required_and_checked_before_any_extraction(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    archive = export_archive(source_state, tmp_path / "out.zip")
    importer, store, paths = make_importer(target_state)
    session_id = upload_archive(store, archive)

    with pytest.raises(ImportRejectedError) as missing:
        importer.stage(session_id, passphrase=None, skip_secrets=False)
    with pytest.raises(ImportRejectedError) as wrong:
        importer.stage(session_id, passphrase="not the passphrase", skip_secrets=False)

    assert missing.value.code == "passphrase_required"
    assert wrong.value.code == "wrong_passphrase"
    assert not (paths.staging / session_id).exists()
    assert store.get(session_id).state == "uploading"  # the upload survives for a retry


def test_stage_grafts_target_posture_rekeys_secrets_and_neutralizes(
    source_state: Path, target_state: Path, tmp_path: Path
) -> None:
    report, _, store, session_id = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))
    staged = ArchivePaths(target_state).staging / session_id / "data.db"

    # Host-bound rows stay the target's, never the source's.
    assert query_rows(staged, "SELECT id FROM api_keys") == [("tk1",)]
    assert query_rows(staged, "SELECT id FROM agent_secrets") == [("ts1",)]
    assert read_config(staged, "channelInstances") == {"telegram": ["target-only"]}
    telegram = read_config(staged, "telegramCredentials")
    assert isinstance(telegram, str)
    assert ConfigCrypto.decrypt_value(telegram, TARGET_KEY) == {"bot": "target-tg"}

    # Carried secrets are re-keyed to the target; the source key no longer opens them.
    providers = read_config(staged, "providers")
    assert isinstance(providers, str)
    assert ConfigCrypto.decrypt_value(providers, TARGET_KEY) == {"openai": "sk-source-provider"}
    with pytest.raises(DecryptionError):
        ConfigCrypto.decrypt_value(providers, SOURCE_KEY)
    assert read_config(staged, "onboarding") == {"done": True}

    # Share links, whitelisted keys and in-flight state never arrive.
    assert query_rows(staged, "SELECT share_token_fingerprint, share_token_expires_at, share_token_protected FROM chats") == [
        (None, None, 0)
    ]
    assert query_rows(staged, "SELECT whitelist_api_keys FROM message_filter_config") == [("[]",)]
    assert query_rows(staged, "SELECT COUNT(*) FROM artifact_share_records") == [(0,)]
    assert query_rows(staged, "SELECT status FROM cron_jobs") == [("paused",)]

    assert report.paused_jobs == 1
    assert report.counts["chats"] == 1
    assert report.counts["skills"] == 1
    assert report.counts["wiki_pages"] == 1
    assert report.executable == {"scheduled_commands": 1, "mcp_stdio_servers": 1, "skill_scripts": 1}
    assert report.missing_paths == 1
    assert report.config_key_carried is True
    assert not report.identity_dropped
    assert "config:telegramCredentials" in report.reentry
    assert not store.archive_path(session_id).exists()  # verified staging replaces the upload


def test_identity_bound_rows_are_dropped_for_a_different_user(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    report, _, _, session_id = stage_archive(
        target_state, export_archive(source_state, tmp_path / "out.zip"), user_id="someone-else"
    )
    staged = ArchivePaths(target_state).staging / session_id / "data.db"

    assert report.identity_dropped is True
    assert query_rows(staged, "SELECT COUNT(*) FROM commitments") == [(0,)]


def test_sandbox_target_never_receives_secrets(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    report, _, _, session_id = stage_archive(
        target_state, export_archive(source_state, tmp_path / "out.zip"), target_key=None, passphrase=None
    )
    staged = ArchivePaths(target_state).staging / session_id / "data.db"

    assert report.config_key_carried is False
    providers = read_config(staged, "providers")
    assert isinstance(providers, str)  # the target's own row (grafted), not the archive's
    assert ConfigCrypto.decrypt_value(providers, TARGET_KEY) == {"openai": "sk-target-provider"}
    assert "config:providers" in report.reentry


def test_newer_schema_is_rejected_and_staging_cleaned(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    archive = export_archive(source_state, tmp_path / "out.zip")
    importer, store, paths = make_importer(target_state, max_version=2)
    session_id = upload_archive(store, archive)

    with pytest.raises(ImportRejectedError) as rejected:
        importer.stage(session_id, passphrase=PASSPHRASE, skip_secrets=False)

    assert rejected.value.code == "newer_schema"
    assert not (paths.staging / session_id).exists()


def test_corrupt_database_is_rejected(target_state: Path, tmp_path: Path) -> None:
    fake = tmp_path / "fake.db"
    fake.write_bytes(b"this is not sqlite" * 100)
    archive = tmp_path / "bad.zip"
    with ArchiveWriter(archive, producer={"name": "t"}) as writer:
        writer.add_file(fake, "data.db")
        writer.finalize()
    importer, store, _ = make_importer(target_state)
    session_id = upload_archive(store, archive)

    with pytest.raises(ImportRejectedError) as rejected:
        importer.stage(session_id, passphrase=None, skip_secrets=False)

    assert rejected.value.code == "corrupt"


def test_hostile_archive_cannot_plant_keys_posture_or_markers(target_state: Path, tmp_path: Path) -> None:
    db = tmp_path / "src" / "data.db"
    create_instance_db(db).close()
    payload = tmp_path / "payload.txt"
    payload.write_text("planted")
    archive = tmp_path / "hostile.zip"
    with ArchiveWriter(archive, producer={"name": "t"}) as writer:
        writer.add_sqlite(db, "data.db")
        for rel in (".encryption_key", "webui/admin.json", "instance_archive/pending.json", "data.db-wal"):
            writer.add_file(payload, rel)
        writer.finalize()

    _, importer, _, session_id = stage_archive(target_state, archive, passphrase=None)
    staging = ArchivePaths(target_state).staging / session_id

    assert sorted(p.name for p in staging.iterdir()) == ["data.db"]


def test_confirm_requires_acknowledgement_of_executable_content(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    _, importer, _, session_id = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))

    with pytest.raises(ImportRejectedError) as rejected:
        importer.confirm(session_id, acknowledge_executables=False)

    assert rejected.value.code == "acknowledgement_required"
    assert not ArchivePaths(target_state).pending.exists()


def test_pending_swap_waits_while_the_requester_is_alive(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    _, importer, _, session_id = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))
    importer.confirm(session_id, acknowledge_executables=True)

    outcome = run_pending_promotion(target_state, wait_seconds=0)

    assert outcome is not None
    assert outcome.status is OutcomeStatus.WAITING
    assert ArchivePaths(target_state).pending.exists()
    assert query_rows(target_state / "data.db", "SELECT id FROM chats") == [("t1",)]


def test_promotion_replaces_data_keeps_host_identity_and_rolls_back(
    source_state: Path, target_state: Path, tmp_path: Path, dead_requester: Callable[[Path], None]
) -> None:
    _, importer, _, session_id = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))
    pending = importer.confirm(session_id, acknowledge_executables=True)
    assert ".encryption_key" not in pending.entries
    assert "webui" not in pending.entries
    dead_requester(target_state)
    paths = ArchivePaths(target_state)

    outcome = run_pending_promotion(target_state, wait_seconds=0)

    assert outcome is not None
    assert outcome.status is OutcomeStatus.RESTORED
    assert outcome.rollback_available is True
    assert not paths.pending.exists()
    assert query_rows(target_state / "data.db", "SELECT id FROM chats") == [("c1",)]
    assert (target_state / "wiki" / "page.md").read_text() == "# page"
    assert not (target_state / "target_only_dir").exists()
    assert (target_state / ".encryption_key").read_text() == "TARGET-MASTER-KEY"
    assert read_outcome(target_state) == outcome
    acknowledge_outcome(target_state)
    assert read_outcome(target_state) is None

    assert prepare_rollback(target_state) is not None
    dead_requester(target_state)
    undone = run_pending_promotion(target_state, wait_seconds=0)

    assert undone is not None
    assert undone.status is OutcomeStatus.RESTORED
    assert undone.rollback_available is False
    assert query_rows(target_state / "data.db", "SELECT id FROM chats") == [("t1",)]
    assert (target_state / "target_only_dir" / "x.txt").read_text() == "old"
    assert not (target_state / "wiki").exists()
    assert prepare_rollback(target_state) is None


def test_semantic_memory_content_survives_a_round_trip_while_the_vector_store_is_live(
    source_state: Path, target_state: Path, tmp_path: Path, dead_requester: Callable[[Path], None]
) -> None:
    live_store = QdrantClient(path=str(source_state / "qdrant"))  # the running app holds the store open
    try:
        archive = export_archive(source_state, tmp_path / "out.zip")
    finally:
        live_store.close()
    _, importer, _, session_id = stage_archive(target_state, archive)
    importer.confirm(session_id, acknowledge_executables=True)
    dead_requester(target_state)

    outcome = run_pending_promotion(target_state, wait_seconds=0)

    assert outcome is not None
    assert outcome.status is OutcomeStatus.RESTORED
    assert read_memory_contents(target_state / "qdrant") == sorted(MEMORY_CONTENTS)
