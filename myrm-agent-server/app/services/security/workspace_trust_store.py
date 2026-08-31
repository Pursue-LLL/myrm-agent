"""Persistent workspace trust store backed by UserConfig.

[INPUT]
- app.services.config.service::config_service (POS: UserConfig persistence)
- myrm_agent_harness.agent.security.workspace_trust::manifest, types (POS: canonical paths + levels)

[OUTPUT]
- WorkspaceTrustStore: in-memory cache + async persist
- ConfigWorkspaceTrustLookup: WorkspaceTrustLookup for harness provider injection

[POS]
Server-side registry for folder trust decisions. Harness reads via lookup at run start.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from myrm_agent_harness.agent.security.workspace_trust.manifest import (
    build_workspace_trust_manifest,
    canonicalize_workspace_path,
    manifest_hash,
)
from myrm_agent_harness.agent.security.workspace_trust.types import (
    WorkspaceTrustEntry,
    WorkspaceTrustLevel,
    WorkspaceTrustManifest,
)

logger = logging.getLogger(__name__)

WORKSPACE_TRUST_CONFIG_KEY = "workspaceTrust.v1"
_DEVICE_ID = "server"


class WorkspaceTrustStore:
    """User-scoped workspace trust registry with in-memory cache."""

    def __init__(self) -> None:
        self._entries: dict[str, WorkspaceTrustEntry] = {}
        self._version: str | None = None
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        from app.services.config.service import config_service

        record = await config_service.get(WORKSPACE_TRUST_CONFIG_KEY)
        self._entries.clear()
        if record is None:
            self._version = None
            self._loaded = True
            return

        self._version = record.version
        raw_entries = record.value.get("entries")
        if not isinstance(raw_entries, dict):
            self._loaded = True
            return

        for path, payload in raw_entries.items():
            if not isinstance(payload, dict):
                continue
            level_raw = payload.get("level")
            decided_at = payload.get("decided_at")
            if not isinstance(level_raw, str) or not isinstance(decided_at, str):
                continue
            try:
                level = WorkspaceTrustLevel(level_raw)
            except ValueError:
                continue
            manifest_hash_val = payload.get("manifest_hash")
            self._entries[str(path)] = WorkspaceTrustEntry(
                path=str(path),
                level=level,
                decided_at=decided_at,
                manifest_hash=str(manifest_hash_val) if manifest_hash_val else "",
            )
        self._loaded = True

    async def _persist(self) -> None:
        from app.services.config.service import config_service

        payload: dict[str, Any] = {
            "entries": {
                path: {
                    "level": entry.level.value,
                    "decided_at": entry.decided_at,
                    "manifest_hash": entry.manifest_hash,
                }
                for path, entry in self._entries.items()
            }
        }
        record = await config_service.set(
            WORKSPACE_TRUST_CONFIG_KEY,
            payload,
            device_id=_DEVICE_ID,
            expected_version=self._version,
        )
        self._version = record.version

    def normalize_path(self, raw_path: str) -> str:
        try:
            return canonicalize_workspace_path(raw_path)
        except ValueError:
            return ""

    def get_level(self, canonical_path: str) -> WorkspaceTrustLevel | None:
        entry = self._entries.get(canonical_path)
        return entry.level if entry else None

    def get_entry(self, canonical_path: str) -> WorkspaceTrustEntry | None:
        return self._entries.get(canonical_path)

    def list_entries(self) -> list[WorkspaceTrustEntry]:
        return sorted(self._entries.values(), key=lambda e: e.decided_at, reverse=True)

    async def build_manifest(self, raw_path: str) -> WorkspaceTrustManifest:
        canonical = self.normalize_path(raw_path)
        if not canonical:
            raise ValueError("workspace path must be absolute")
        current = self.get_level(canonical)
        return build_workspace_trust_manifest(raw_path, current_level=current)

    async def decide(
        self,
        raw_path: str,
        level: WorkspaceTrustLevel,
        *,
        manifest: WorkspaceTrustManifest | None = None,
    ) -> WorkspaceTrustEntry:
        if not self._loaded:
            await self.load()

        canonical = self.normalize_path(raw_path)
        if not canonical:
            raise ValueError("workspace path must be absolute")

        decided_at = datetime.now(UTC).isoformat()
        hash_value = manifest_hash(manifest) if manifest else ""
        entry = WorkspaceTrustEntry(
            path=canonical,
            level=level,
            decided_at=decided_at,
            manifest_hash=hash_value,
        )
        self._entries[canonical] = entry
        await self._persist()
        return entry

    async def revoke(self, raw_path: str) -> WorkspaceTrustEntry | None:
        if not self._loaded:
            await self.load()

        canonical = self.normalize_path(raw_path)
        if not canonical:
            raise ValueError("workspace path must be absolute")

        existing = self._entries.get(canonical)
        if existing is None:
            return None

        entry = WorkspaceTrustEntry(
            path=canonical,
            level=WorkspaceTrustLevel.REVOKED,
            decided_at=datetime.now(UTC).isoformat(),
            manifest_hash=existing.manifest_hash,
        )
        self._entries[canonical] = entry
        await self._persist()
        return entry

    async def remove(self, raw_path: str) -> bool:
        if not self._loaded:
            await self.load()

        canonical = self.normalize_path(raw_path)
        if not canonical or canonical not in self._entries:
            return False
        del self._entries[canonical]
        await self._persist()
        return True


_store: WorkspaceTrustStore | None = None


def get_workspace_trust_store() -> WorkspaceTrustStore:
    global _store
    if _store is None:
        _store = WorkspaceTrustStore()
    return _store


class ConfigWorkspaceTrustLookup:
    """Adapter exposing WorkspaceTrustStore as a harness WorkspaceTrustLookup."""

    def __init__(self, store: WorkspaceTrustStore) -> None:
        self._store = store

    def normalize_path(self, raw_path: str) -> str:
        return self._store.normalize_path(raw_path)

    def get_level(self, canonical_path: str) -> WorkspaceTrustLevel | None:
        return self._store.get_level(canonical_path)


async def init_workspace_trust_store() -> None:
    """Load persisted trust decisions and register harness lookup."""
    from myrm_agent_harness.agent.security.workspace_trust.provider import (
        set_workspace_trust_lookup,
    )

    store = get_workspace_trust_store()
    await store.load()
    set_workspace_trust_lookup(ConfigWorkspaceTrustLookup(store))
    logger.info("Workspace trust store: loaded %d entries", len(store.list_entries()))
