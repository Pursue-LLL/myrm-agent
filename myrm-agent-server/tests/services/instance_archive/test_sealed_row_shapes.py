"""A secret row travels in an archive, and opens on the target, in every shape the config service has stored it.

[INPUT]
app.services.instance_archive.export_service::build_export (POS: decides which sealed rows travel under the passphrase)
app.services.instance_archive.stage_db (POS: re-keys the rows that travelled to the target instance's key)
app.services.config.service::ConfigService, _decrypt_if_needed (POS: the writer and the reader of the stored rows)

[OUTPUT]
That a row stored as ``{"_cipher": ...}`` (what ``ConfigService.set`` writes), as the bare ciphertext string, and as an
envelope sealed a second time under the same key (what the startup sweep of an older build left behind) is carried when
the user sets a passphrase, and that after the import the target reads exactly one layer under its own key.

[POS]
The archive tests seal their rows by hand as a bare string; this file stores them the way the writer does, because a
shape the exporter did not recognise silently dropped the keys (or, for a second layer, carried a layer that the
target could not open).
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from myrm_agent_harness.utils.crypto import ConfigCrypto
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import migration, service
from app.services.config.encryption import ConfigEncryptionService
from app.services.instance_archive import ArchivePaths
from tests.services.instance_archive.archive_flow import export_archive, read_config, stage_archive
from tests.services.instance_archive.conftest import SOURCE_KEY, TARGET_KEY, create_instance_db

_PLAIN = {"openai": "sk-real-writer-secret"}


def _envelope(plain: dict[str, object], key: bytes) -> str:
    return json.dumps({"_cipher": ConfigCrypto.encrypt_value(plain, key)})


def _bare_string(plain: dict[str, object], key: bytes) -> str:
    return json.dumps(ConfigCrypto.encrypt_value(plain, key))


def _second_layer(plain: dict[str, object], key: bytes) -> str:
    inner = ConfigCrypto.encrypt_value(plain, key)
    return json.dumps(ConfigCrypto.encrypt_value({"_cipher": inner}, key))


_SHAPES: dict[str, Callable[[dict[str, object], bytes], str]] = {
    "envelope": _envelope,
    "bare string": _bare_string,
    "second layer": _second_layer,
}


def _carried_and_reentry(archive: Path, tmp_path: Path) -> tuple[object, list[str]]:
    extracted = tmp_path / "extracted.db"
    with zipfile.ZipFile(archive) as zf:
        extracted.write_bytes(zf.read("payload/data.db"))
        metadata = json.loads(zf.read("manifest.json"))["metadata"]
    return read_config(extracted, "providers"), metadata["reentry"]


def _read_on_target(staged_row: object) -> dict[str, object]:
    """The row as the target's config service reads it, under the target key."""
    assert isinstance(staged_row, str)
    return ConfigCrypto.decrypt_value(staged_row, TARGET_KEY)


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_a_sealed_row_is_carried_and_opens_on_the_target_whatever_shape_it_was_stored_in(
    shape: str, source_state: Path, target_state: Path, tmp_path: Path
) -> None:
    conn = __import__("sqlite3").connect(source_state / "data.db")
    conn.execute("DELETE FROM user_configs WHERE config_key = 'providers'")
    conn.execute(
        "INSERT INTO user_configs (id, config_key, config_value, is_encrypted) VALUES ('id-providers', 'providers', ?, 1)",
        (_SHAPES[shape](_PLAIN, SOURCE_KEY),),
    )
    conn.commit()
    conn.close()
    archive = export_archive(source_state, tmp_path / "out.zip")

    carried, reentry = _carried_and_reentry(archive, tmp_path)
    assert carried is not None, shape
    assert "config:providers" not in reentry

    _, _, _, session_id = stage_archive(target_state, archive)
    staged = ArchivePaths(target_state).staging / session_id / "data.db"
    assert _read_on_target(read_config(staged, "providers")) == _PLAIN


@pytest.fixture
async def real_writer_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Path]:
    """A source instance whose rows are written by the real ``ConfigService`` into a file database."""
    state = tmp_path / "real-writer"
    conn = create_instance_db(state / "data.db")
    conn.execute("DROP TABLE user_configs")
    conn.commit()
    conn.close()
    sync_engine = create_engine(f"sqlite:///{state / 'data.db'}")
    UserConfig.__table__.create(sync_engine)
    ConfigAuditLog.__table__.create(sync_engine)
    sync_engine.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{state / 'data.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sealing = ConfigEncryptionService(encryption_key=SOURCE_KEY, is_sandbox=False, is_local=True)
    monkeypatch.setattr(migration, "get_encryption_service", lambda: sealing)
    monkeypatch.setattr(service, "get_encryption_service", lambda: sealing)

    @asynccontextmanager
    async def session() -> AsyncGenerator[AsyncSession]:
        async with factory() as db:
            yield db

    monkeypatch.setattr("app.database.connection.get_session", session)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    yield state
    await engine.dispose()


@pytest.mark.parametrize("restarts", [0, 1, 2])
async def test_a_row_saved_by_the_config_service_survives_restarts_and_travels(
    restarts: int, real_writer_source: Path, target_state: Path, tmp_path: Path
) -> None:
    await service.ConfigService().set("providers", dict(_PLAIN), "browser")
    for _ in range(restarts):
        await migration.seal_stored_configs()

    archive = export_archive(real_writer_source, tmp_path / "out.zip")

    carried, reentry = _carried_and_reentry(archive, tmp_path)
    assert carried is not None and "config:providers" not in reentry
    _, _, _, session_id = stage_archive(target_state, archive)
    staged = ArchivePaths(target_state).staging / session_id / "data.db"
    assert _read_on_target(read_config(staged, "providers")) == _PLAIN
