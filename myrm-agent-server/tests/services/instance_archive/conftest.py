"""Shared fixtures: a minimal instance database and helpers to drive pre-boot promotion."""

from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from myrm_agent_harness.utils.crypto import ConfigCrypto
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.services.instance_archive.models import ArchivePaths, PendingPromotion

SOURCE_KEY = ConfigCrypto.derive_key("source-instance-key")
TARGET_KEY = ConfigCrypto.derive_key("target-instance-key")

# Permission bits only restrict a user who is not root, and only on a POSIX file system.
PERMISSIONS_ENFORCED = sys.platform != "win32" and os.geteuid() != 0

_SCHEMA = """
CREATE TABLE _schema_migrations (version INTEGER, applied_at TIMESTAMP, duration_ms REAL, checksum VARCHAR(64));
CREATE TABLE chats (
    id TEXT PRIMARY KEY, title TEXT,
    share_token_fingerprint TEXT, share_token_expires_at INTEGER, share_token_protected BOOLEAN
);
CREATE TABLE messages (id TEXT PRIMARY KEY, chat_id TEXT, content TEXT);
CREATE TABLE agents (id TEXT PRIMARY KEY, home_directory TEXT);
CREATE TABLE cron_jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, command TEXT);
CREATE TABLE user_configs (
    id TEXT PRIMARY KEY, config_key TEXT NOT NULL UNIQUE, config_value JSON NOT NULL,
    version TEXT NOT NULL DEFAULT '1', last_device_id TEXT NOT NULL DEFAULT 'd', is_encrypted BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE message_filter_config (id INTEGER PRIMARY KEY, whitelist_api_keys JSON NOT NULL);
CREATE TABLE api_keys (id TEXT PRIMARY KEY, label TEXT, extra TEXT);
CREATE TABLE agent_secrets (id TEXT PRIMARY KEY, value TEXT);
CREATE TABLE artifact_share_records (id TEXT PRIMARY KEY, share_path TEXT);
CREATE TABLE commitments (id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
"""


MEMORY_COLLECTION = "_semantic_memory"
MEMORY_CONTENTS = ("prefers green tea", "works in Hangzhou", "deploys on Fridays")


def seed_memory_vectors(path: Path) -> None:
    """A real embedded Qdrant store: the payloads are the only copy of semantic memory content."""
    client = QdrantClient(path=str(path))
    try:
        client.create_collection(MEMORY_COLLECTION, vectors_config=VectorParams(size=4, distance=Distance.COSINE))
        client.upsert(
            MEMORY_COLLECTION,
            points=[
                PointStruct(id=index, vector=[0.1 * index, 0.2, 0.3, 0.4], payload={"content": content})
                for index, content in enumerate(MEMORY_CONTENTS, start=1)
            ],
        )
    finally:
        client.close()


def read_memory_contents(path: Path) -> list[str]:
    client = QdrantClient(path=str(path))
    try:
        points, _ = client.scroll(MEMORY_COLLECTION, limit=100)
        return sorted(str(point.payload["content"]) for point in points if point.payload)
    finally:
        client.close()


def seal_config(plain: dict[str, object], key: bytes) -> str:
    """How user_configs stores an encrypted row: the ciphertext string, JSON-encoded."""
    return json.dumps(ConfigCrypto.encrypt_value(plain, key))


def create_instance_db(path: Path, *, version: int = 5) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.executemany("INSERT INTO _schema_migrations (version) VALUES (?)", [(v,) for v in range(version + 1)])
    conn.commit()
    return conn


def put_config(conn: sqlite3.Connection, key: str, value: object, *, encrypted: bool = False) -> None:
    raw = value if isinstance(value, str) and encrypted else json.dumps(value)
    conn.execute(
        "INSERT INTO user_configs (id, config_key, config_value, is_encrypted) VALUES (?, ?, ?, ?)",
        (f"id-{key}", key, raw, int(encrypted)),
    )


@pytest.fixture
def source_state(tmp_path: Path) -> Path:
    """A populated source instance: data, secrets, host-bound rows, files and excluded paths."""
    state = tmp_path / "source"
    conn = create_instance_db(state / "data.db")
    conn.execute("INSERT INTO chats VALUES ('c1', 'hello', 'fp-123', 999, 1)")
    conn.execute("INSERT INTO messages VALUES ('m1', 'c1', 'hi there')")
    conn.execute("INSERT INTO agents VALUES ('a1', '/definitely/not/here')")
    conn.execute("INSERT INTO cron_jobs VALUES ('j1', 'active', 'echo run')")
    conn.execute("INSERT INTO message_filter_config VALUES (1, '[\"sk-whitelisted\"]')")
    conn.execute("INSERT INTO api_keys VALUES ('k1', 'source-key-label', 'source-secret')")
    conn.execute("INSERT INTO agent_secrets VALUES ('s1', 'source-agent-secret')")
    conn.execute("INSERT INTO artifact_share_records VALUES ('r1', '/share/x')")
    conn.execute("INSERT INTO commitments VALUES ('cm1', 'user-a')")
    put_config(conn, "providers", seal_config({"openai": "sk-source-provider"}, SOURCE_KEY), encrypted=True)
    put_config(
        conn,
        "mcpServers",
        seal_config({"servers": {"fs": {"command": "npx", "args": ["x"]}}}, SOURCE_KEY),
        encrypted=True,
    )
    put_config(conn, "telegramCredentials", seal_config({"bot": "tg-secret"}, SOURCE_KEY), encrypted=True)
    put_config(conn, "channelInstances", {"telegram": ["a"]})
    put_config(conn, "onboarding", {"done": True})
    conn.execute("INSERT INTO chats VALUES ('gone', 'RESIDUE-SECRET-MARKER', NULL, NULL, 0)")
    conn.commit()
    conn.execute("DELETE FROM chats WHERE id = 'gone'")
    conn.commit()
    conn.close()

    (state / "wiki").mkdir()
    (state / "wiki" / "page.md").write_text("# page")
    (state / "skills" / "demo" / "scripts").mkdir(parents=True)
    (state / "skills" / "demo" / "scripts" / "run.sh").write_text("echo hi")
    (state / "harness" / "workspace" / "proj").mkdir(parents=True)
    (state / "harness" / "workspace" / "proj" / "token-notes.txt").write_text("user notes")
    (state / "harness" / "workspace" / "node_modules" / "dep").mkdir(parents=True)
    (state / "harness" / "workspace" / "node_modules" / "dep" / "index.js").write_text("x")
    (state / ".encryption_key").write_text("SOURCE-MASTER-KEY")
    (state / "whatsapp_auth").mkdir()
    (state / "whatsapp_auth" / "creds.json").write_text("{}")
    (state / "session_vault").mkdir()
    (state / "session_vault" / "site.enc").write_bytes(b"x")
    (state / "webui").mkdir()
    (state / "webui" / "admin.json").write_text("{}")
    seed_memory_vectors(state / "qdrant")
    (state / "unknown_store.db").write_bytes(b"")
    return state


@pytest.fixture
def target_state(tmp_path: Path) -> Path:
    """A target instance with its own security posture and secrets."""
    state = tmp_path / "target"
    conn = create_instance_db(state / "data.db")
    conn.execute("INSERT INTO chats VALUES ('t1', 'target chat', NULL, NULL, 0)")
    conn.execute("INSERT INTO api_keys VALUES ('tk1', 'target-key-label', 'target-secret')")
    conn.execute("INSERT INTO agent_secrets VALUES ('ts1', 'target-agent-secret')")
    put_config(conn, "providers", seal_config({"openai": "sk-target-provider"}, TARGET_KEY), encrypted=True)
    put_config(conn, "telegramCredentials", seal_config({"bot": "target-tg"}, TARGET_KEY), encrypted=True)
    put_config(conn, "channelInstances", {"telegram": ["target-only"]})
    conn.commit()
    conn.close()
    (state / ".encryption_key").write_text("TARGET-MASTER-KEY")
    (state / "target_only_dir").mkdir()
    (state / "target_only_dir" / "x.txt").write_text("old")
    return state


@pytest.fixture
def dead_requester() -> Callable[[Path], None]:
    """Rewrite the pending marker so its requester is a process that has already exited."""

    def _apply(state_dir: Path) -> None:
        paths = ArchivePaths(state_dir)
        pending = PendingPromotion.load(paths.pending)
        assert pending is not None
        proc = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True, check=True)
        dead = dataclasses.replace(pending, requester_pid=int(proc.stdout.strip()), requester_started_at=1.0)
        dead.save(paths.pending)

    return _apply
