"""Prepare a staged data.db copy before it replaces the live database.

[INPUT]
- app.services.instance_archive.table_policy (POS: which rows travel)
- app.services.instance_archive.checkpoint_scrub::scrub_checkpoint_threads (POS: web incognito threads leave the staged checkpoints.db)
- myrm_agent_harness.utils.crypto::ConfigCrypto (POS: re-encrypt carried config rows)
- sqlite3: ATTACH of the live database as a read-only graft source

[OUTPUT]
- StageContext / StagedDbResult / StageRejected
- prepare_staged_db: verify, scrub (also the sibling checkpoints.db), neutralize, graft host-bound rows, summarize (archive vs live counts)
- verify_instance_db: integrity + schema gate for any database about to go live

[POS]
Runs at stage time while the live app is up, so grafting uses the current live
schema. The archive is untrusted input: the scrub is re-applied here and every
rule is enforced again regardless of what the exporter claimed. Result: the
target's security posture and machine-bound secrets survive an import, imported
scheduled jobs come up paused, and carried secrets are re-keyed to the target.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError, EncryptionError

from app.services.instance_archive.checkpoint_scrub import CHECKPOINTS_DB_NAME, scrub_checkpoint_threads
from app.services.instance_archive.table_policy import (
    HOST_BOUND_TABLES,
    IDENTITY_TABLES,
    SECRET_TABLES,
    ConfigRowPolicy,
    column_names,
    config_needs_reentry,
    config_row_policy,
    count_rows,
    delete_all_rows,
    scrub_sensitive_surface,
    table_names,
    web_incognito_chat_ids,
)

logger = logging.getLogger(__name__)

# Table names double as the count keys the frontend report renders (frontend `COUNT_KEYS`).
_SUMMARY_TABLES = ("chats", "messages", "agents", "cron_jobs")
# The chat total matches the app's chat list, which hides trashed and incognito chats.
_LISTED_CHAT_COLUMNS = frozenset({"deleted_at", "is_incognito"})
_LISTED_CHATS = " WHERE deleted_at IS NULL AND is_incognito = 0"
_PATH_COLUMNS = (
    ("agents", "home_directory"),
    ("projects", "workspace_path"),
    ("kanban_boards", "default_workdir"),
    ("kanban_tasks", "workspace_path"),
)


class StageRejected(ValueError):
    """The archive's database cannot be imported; ``code`` is a stable machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class StageContext:
    live_db: Path | None
    source_user_id: str | None
    target_user_id: str
    max_schema_version: int
    source_key: bytes | None  # opens the archive's carried config rows; None when none travelled
    target_key: bytes | None  # re-keys them for this instance; None when the target cannot hold secrets


@dataclass(frozen=True, slots=True)
class StagedDbResult:
    counts: dict[str, int]
    current_counts: dict[str, int]  # the same tables in the live database; empty when it cannot be read
    executable: dict[str, int]
    reentry: tuple[str, ...]
    paused_jobs: int
    missing_paths: int
    identity_dropped: bool
    config_key_carried: bool


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.as_uri(), uri=True)
    conn.execute("PRAGMA secure_delete = ON")
    return conn


def _verify(conn: sqlite3.Connection, max_schema_version: int) -> None:
    try:
        verdict = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise StageRejected("corrupt", "The archived database is unreadable") from exc
    if verdict is None or verdict[0] != "ok":
        raise StageRejected("corrupt", "The archived database failed its integrity check")
    if "_schema_migrations" not in table_names(conn):
        raise StageRejected("not_instance_db", "The archived database is not a Myrm instance database")
    version = conn.execute("SELECT MAX(version) FROM _schema_migrations").fetchone()[0]
    if version is None or int(version) > max_schema_version:
        raise StageRejected("newer_schema", "The archive was created by a newer version of the app")


def verify_instance_db(path: Path, max_schema_version: int) -> None:
    """Integrity + schema-version gate for a database that is about to become live."""
    conn = _connect(path)
    try:
        _verify(conn, max_schema_version)
    finally:
        conn.close()


def _graft(conn: sqlite3.Connection, table: str, where: str = "", params: tuple[str, ...] = ()) -> None:
    """Copy the live rows of ``table`` into the staged copy over the columns both schemas share."""
    if table not in table_names(conn) or table not in table_names(conn, "live"):
        return
    live_columns = set(column_names(conn, table, "live"))
    columns = [c for c in column_names(conn, table) if c in live_columns]
    if not columns:
        return
    quoted = ", ".join(f'"{c}"' for c in columns)
    conn.execute(f'INSERT OR IGNORE INTO main."{table}" ({quoted}) SELECT {quoted} FROM live."{table}" {where}', params)


def _count_commands(node: object) -> int:
    """Count stdio-style entries (anything with a ``command``) in a decrypted MCP config."""
    if isinstance(node, dict):
        own = 1 if isinstance(node.get("command"), str) and node["command"] else 0
        return own + sum(_count_commands(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_commands(v) for v in node)
    return 0


def _rekey_configs(conn: sqlite3.Connection, ctx: StageContext) -> tuple[list[str], int, bool]:
    """Apply the config-row policy; returns (re-entry keys, executable MCP count, whether secrets travelled)."""
    reentry: list[str] = []
    mcp_commands = 0
    carried = False
    rows = conn.execute("SELECT config_key, config_value, is_encrypted FROM user_configs").fetchall()
    for key, raw_value, is_encrypted in rows:
        policy = config_row_policy(key)
        if policy is ConfigRowPolicy.DATA:
            continue
        rekeyed: str | None = None
        if policy is ConfigRowPolicy.PORTABLE_SECRET and is_encrypted and ctx.source_key and ctx.target_key:
            try:
                ciphertext = json.loads(raw_value)
                plain = ConfigCrypto.decrypt_value(ciphertext, ctx.source_key) if isinstance(ciphertext, str) else None
                if plain is not None:
                    rekeyed = json.dumps(ConfigCrypto.encrypt_value(plain, ctx.target_key))
                    if key == "mcpServers":
                        mcp_commands = _count_commands(plain)
            except (ValueError, DecryptionError, EncryptionError):
                rekeyed = None
        if rekeyed is not None:
            conn.execute("UPDATE user_configs SET config_value = ? WHERE config_key = ?", (rekeyed, key))
            carried = True
            continue
        conn.execute("DELETE FROM user_configs WHERE config_key = ?", (key,))
        if config_needs_reentry(key):
            reentry.append(f"config:{key}")
    return reentry, mcp_commands, carried


def _graft_live_config_rows(conn: sqlite3.Connection) -> None:
    """Rows the archive did not bring and the target must keep: its own secrets and host settings."""
    if "user_configs" not in table_names(conn, "live"):
        return
    present = {row[0] for row in conn.execute("SELECT config_key FROM main.user_configs")}
    for (key,) in conn.execute("SELECT config_key FROM live.user_configs").fetchall():
        if key not in present and config_row_policy(key) is not ConfigRowPolicy.DATA:
            _graft(conn, "user_configs", "WHERE config_key = ?", (key,))


def _summary_counts(conn: sqlite3.Connection, schema: str = "main") -> dict[str, int]:
    """Counts the restore review shows for the tables of ``schema``, measured the same way on both sides."""
    existing = table_names(conn, schema)
    counts: dict[str, int] = {}
    for table in _SUMMARY_TABLES:
        if table not in existing:
            continue
        listed = table == "chats" and _LISTED_CHAT_COLUMNS <= set(column_names(conn, table, schema))
        counts[table] = count_rows(conn, table, schema, _LISTED_CHATS if listed else "")
    return counts


def _live_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Counts of the attached live database (informational only); empty when it cannot be read."""
    try:
        return _summary_counts(conn, "live")
    except sqlite3.Error as exc:
        logger.warning("Could not count live rows for the restore review: %s", exc)
        return {}


def _missing_paths(conn: sqlite3.Connection) -> int:
    existing = table_names(conn)
    missing: set[str] = set()
    for table, column in _PATH_COLUMNS:
        if table not in existing or column not in column_names(conn, table):
            continue
        for (value,) in conn.execute(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'):
            if isinstance(value, str) and os.path.isabs(value) and not os.path.exists(value):
                missing.add(value)
    return len(missing)


def prepare_staged_db(staged_db: Path, ctx: StageContext) -> StagedDbResult:
    conn = _connect(staged_db)
    try:
        _verify(conn, ctx.max_schema_version)
        existing = table_names(conn)
        incognito_chat_ids = web_incognito_chat_ids(conn)
        scrub_sensitive_surface(conn)
        reentry = [f"table:{t}" for t, n in delete_all_rows(conn, SECRET_TABLES).items() if n]
        delete_all_rows(conn, HOST_BOUND_TABLES)
        identity_dropped = ctx.source_user_id != ctx.target_user_id
        if identity_dropped:
            delete_all_rows(conn, IDENTITY_TABLES)
        paused_jobs = 0
        scheduled_commands = 0
        if "cron_jobs" in existing:
            paused_jobs = conn.execute("UPDATE cron_jobs SET status = 'paused' WHERE status = 'active'").rowcount
            scheduled_commands = int(
                conn.execute("SELECT COUNT(*) FROM cron_jobs WHERE command IS NOT NULL AND command != ''").fetchone()[0]
            )
        mcp_commands = 0
        config_key_carried = False
        if "user_configs" in existing:
            config_reentry, mcp_commands, config_key_carried = _rekey_configs(conn, ctx)
            reentry.extend(config_reentry)
        current_counts: dict[str, int] = {}
        if ctx.live_db is not None and ctx.live_db.exists():
            conn.commit()  # ATTACH is illegal inside an open transaction
            conn.execute("ATTACH DATABASE ? AS live", (f"{ctx.live_db.as_uri()}?mode=ro",))
            for table in sorted(HOST_BOUND_TABLES | SECRET_TABLES):
                _graft(conn, table)
            _graft_live_config_rows(conn)
            conn.commit()
            current_counts = _live_counts(conn)
            conn.execute("DETACH DATABASE live")
        counts = _summary_counts(conn)
        missing_paths = _missing_paths(conn)
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    checkpoints = staged_db.with_name(CHECKPOINTS_DB_NAME)
    if checkpoints.exists():
        scrub_checkpoint_threads(checkpoints, incognito_chat_ids)
    return StagedDbResult(
        counts=counts,
        current_counts=current_counts,
        executable={"scheduled_commands": scheduled_commands, "mcp_stdio_servers": mcp_commands},
        reentry=tuple(reentry),
        paused_jobs=paused_jobs,
        missing_paths=missing_paths,
        identity_dropped=identity_dropped,
        config_key_carried=config_key_carried,
    )
