"""data.db table policy and the scrub applied to every archived copy.

[INPUT]
- sqlite3: operates on a detached copy, never on the live database
- app.services.config.encryption::is_sensitive_config (POS: which user_configs rows are encrypted)
- app.services.chat.chat_bound_rows::CHAT_BOUND_TABLES (POS: plain tables whose rows belong to one chat)

[OUTPUT]
- HOST_BOUND_TABLES / SECRET_TABLES / EPHEMERAL_TABLES / IDENTITY_TABLES
- CARRIED_SENSITIVE_CONFIG_KEYS / HOST_BOUND_CONFIG_KEYS / config_row_policy / config_needs_reentry
- scrub_sensitive_surface: web incognito chats, share links, whitelist keys, in-flight work (shared by export and staging)
- web_incognito_chat_ids: the chats scrub_sensitive_surface removes, for the stores outside data.db that key by chat
- live_web_incognito_chat_ids: the same chats read from the running instance's database (checkpoints, workspace files)
- surviving_chat_ids / live_surviving_chat_ids: the chats an archive keeps (all but the web incognito ones), for the file store
- count_rows / table_names / column_names: small sqlite helpers

[POS]
Single source of truth for "which data.db rows travel". Default is data: a table
is carried unless it is listed here. Host-bound tables keep the *target's* rows
(an archive never loosens the target's security posture); secret tables and
in-flight tables are dropped. The CI reconciliation test pins every name below
to the live schema so renames cannot silently void the policy.
"""

from __future__ import annotations

import sqlite3
from enum import StrEnum
from pathlib import Path

from app.services.chat.chat_bound_rows import CHAT_BOUND_TABLES
from app.services.config.encryption import is_sensitive_config

# Rows describing the security posture / integrations of the host: the target keeps its own.
HOST_BOUND_TABLES: frozenset[str] = frozenset(
    {
        "user_tool_allowlist",
        "skill_permission_grants",
        "risk_rules",
        "risk_hits",
        "security_profiles",
        "approvals",
        "channel_pairings",
        "a2a_peers",
        "api_keys",
        "lifecycle_webhooks",
        "web_push_subscriptions",
    }
)

# Bound to this machine's keyring / master key: undecryptable elsewhere, so the user re-enters them.
SECRET_TABLES: frozenset[str] = frozenset({"agent_secrets", "vault_credentials"})

# In-flight or link-style state that is meaningless (or unsafe to resume) on another host.
EPHEMERAL_TABLES: frozenset[str] = frozenset({"artifact_share_records", "interrupted_turn_markers"})

# Rows keyed by user identity: carried only when the importing identity equals the exporting one.
IDENTITY_TABLES: frozenset[str] = frozenset({"commitments", "skill_permission_usage_logs", "artifact_audit_logs"})

# Sensitive user_configs rows that are portable across machines (provider keys, MCP, search).
# Every other sensitive row (channel logins, proxies, org-managed servers) stays with its host.
CARRIED_SENSITIVE_CONFIG_KEYS: frozenset[str] = frozenset(
    {"providers", "retrieval", "searchServices", "mcpServers", "mcpOAuthTokens"}
)

# Non-sensitive config rows that still describe this host (paths, outbound sync, security posture).
HOST_BOUND_CONFIG_KEYS: frozenset[str] = frozenset(
    {"channelInstances", "securityDashboardSettings", "obsidian_vault_binding", "wikiSourceSync"}
)

_CHAT_SHARE_COLUMNS = ("share_token_fingerprint", "share_token_expires_at")

# Web incognito chats are promised to vanish once idle, so no archive may outlive them. Transcript imports
# (source != "web") reuse the flag only to stay out of the sidebar; they are real data and travel.
_INCOGNITO_COLUMNS = frozenset({"is_incognito", "source"})
_WEB_INCOGNITO = "is_incognito = 1 AND source = 'web'"


class ConfigRowPolicy(StrEnum):
    DATA = "data"  # carried as-is
    PORTABLE_SECRET = "portable_secret"  # carried as ciphertext only when an envelope exists
    HOST_BOUND = "host_bound"  # never carried; the target keeps its own row


def config_row_policy(key: str) -> ConfigRowPolicy:
    if key in CARRIED_SENSITIVE_CONFIG_KEYS:
        return ConfigRowPolicy.PORTABLE_SECRET
    if is_sensitive_config(key) or key in HOST_BOUND_CONFIG_KEYS:
        return ConfigRowPolicy.HOST_BOUND
    return ConfigRowPolicy.DATA


def config_needs_reentry(key: str) -> bool:
    """Credential rows the user has to enter again when they do not travel."""
    return key in CARRIED_SENSITIVE_CONFIG_KEYS or key.endswith("Credentials")


def table_names(conn: sqlite3.Connection, schema: str = "main") -> set[str]:
    rows = conn.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type='table'")
    return {row[0] for row in rows}


def column_names(conn: sqlite3.Connection, table: str, schema: str = "main") -> list[str]:
    return [row[1] for row in conn.execute(f'PRAGMA {schema}.table_info("{table}")')]


def count_rows(conn: sqlite3.Connection, table: str, schema: str = "main", where: str = "") -> int:
    """``where`` is an SQL fragment owned by the caller (never user input), e.g. ``" WHERE x IS NULL"``."""
    return int(conn.execute(f'SELECT COUNT(*) FROM {schema}."{table}"{where}').fetchone()[0])


def delete_all_rows(conn: sqlite3.Connection, tables: frozenset[str]) -> dict[str, int]:
    """Empty every listed table that exists; returns the dropped row counts (non-zero only)."""
    dropped: dict[str, int] = {}
    for table in sorted(tables & table_names(conn)):
        count = count_rows(conn, table)
        if count:
            conn.execute(f'DELETE FROM "{table}"')
            dropped[table] = count
    return dropped


def web_incognito_chat_ids(conn: sqlite3.Connection) -> list[str]:
    """Ids of the web incognito chats; none for a database from before the incognito columns."""
    if "chats" not in table_names(conn) or not _INCOGNITO_COLUMNS <= set(column_names(conn, "chats")):
        return []
    return [row[0] for row in conn.execute(f"SELECT id FROM chats WHERE {_WEB_INCOGNITO}")]


def live_web_incognito_chat_ids(main_db: Path) -> list[str]:
    """The web incognito chats of the running instance, read at call time for the stores that sit outside data.db.

    Raises:
        sqlite3.Error: the live database cannot be read, so no caller may assume there are no incognito chats.
    """
    conn = sqlite3.connect(f"{main_db.as_uri()}?mode=ro", uri=True)
    try:
        return web_incognito_chat_ids(conn)
    finally:
        conn.close()


def surviving_chat_ids(conn: sqlite3.Connection) -> set[str]:
    """Ids of the chats an archive keeps: every chat but the web incognito ones."""
    if "chats" not in table_names(conn):
        return set()
    return {row[0] for row in conn.execute("SELECT id FROM chats")} - set(web_incognito_chat_ids(conn))


def live_surviving_chat_ids(main_db: Path) -> set[str]:
    """The chats an archive of the running instance keeps, read at call time for the file store.

    Raises:
        sqlite3.Error: the live database cannot be read, so no caller may assume that every chat is gone.
    """
    conn = sqlite3.connect(f"{main_db.as_uri()}?mode=ro", uri=True)
    try:
        return surviving_chat_ids(conn)
    finally:
        conn.close()


def _drop_web_incognito_chats(conn: sqlite3.Connection, existing: set[str], columns: set[str]) -> None:
    """Delete the web incognito chats with everything stored under their ids.

    Messages, full-text indexes and the recall index hang off ``chats`` through ON DELETE CASCADE (and the FTS
    triggers it fires), which SQLite applies only while foreign keys are on. The pragma is ignored inside an open
    transaction, so pending work is committed first; a switch that did not take effect aborts the scrub because
    orphaned message text would still travel. The plain tables of ``CHAT_BOUND_TABLES`` have no foreign key, so
    their rows go first, while the chat rows still name the ids.
    """
    if not _INCOGNITO_COLUMNS <= columns:
        return
    conn.commit()
    previous = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if not conn.execute("PRAGMA foreign_keys").fetchone()[0]:
            raise sqlite3.OperationalError("Cannot enable foreign keys, so incognito chats would stay behind as orphan rows")
        for bound in CHAT_BOUND_TABLES:
            if bound.table in existing and bound.chat_column in column_names(conn, bound.table):
                conn.execute(
                    f'DELETE FROM "{bound.table}" WHERE "{bound.chat_column}" IN (SELECT id FROM chats WHERE {_WEB_INCOGNITO})'
                )
        conn.execute(f"DELETE FROM chats WHERE {_WEB_INCOGNITO}")
        conn.commit()
    finally:
        conn.execute(f"PRAGMA foreign_keys = {previous}")


def scrub_sensitive_surface(conn: sqlite3.Connection) -> None:
    """Remove web incognito chats, share links, whitelisted API keys and in-flight work from the archived copy."""
    existing = table_names(conn)
    if "chats" in existing:
        columns = set(column_names(conn, "chats"))
        _drop_web_incognito_chats(conn, existing, columns)
        assignments = [f"{c} = NULL" for c in _CHAT_SHARE_COLUMNS if c in columns]
        if "share_token_protected" in columns:
            assignments.append("share_token_protected = 0")
        if assignments:
            conn.execute(f"UPDATE chats SET {', '.join(assignments)}")
    # The table has no ORM model, but an existing database can still hold it with whitelisted API keys.
    if "message_filter_config" in existing:
        conn.execute("UPDATE message_filter_config SET whitelist_api_keys = '[]'")
    delete_all_rows(conn, EPHEMERAL_TABLES)
