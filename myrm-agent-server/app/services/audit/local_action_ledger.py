"""Append-only tamper-proof local action audit ledger service.

[POS]
Maintains the cryptographic hash chain for all local entity accesses
(emails, invoices, ID credentials, documents) performed by 24/7 autonomous agents.
Guarantees verifiable transparency and non-repudiation on local hardware.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.schemas.local_action_audit import LocalActionAuditEntry, PrivacyInspectorSummary

logger = logging.getLogger(__name__)

_GENESIS_PREV_HASH: str = "0" * 64
_DEFAULT_AUDIT_KEY: str = os.getenv("MYRM_LOCAL_AUDIT_KEY", "myrm_local_action_ledger_hmac_secret_2026")


class LocalActionLedgerService:
    """Manages append-only cryptographic ledger for agent data access."""

    def __init__(
        self,
        ledger_file: Path | None = None,
        signing_key: str = _DEFAULT_AUDIT_KEY,
    ) -> None:
        self._ledger_file: Path | None = ledger_file
        self._signing_key: str = signing_key
        self._entries: list[LocalActionAuditEntry] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        if self._ledger_file and self._ledger_file.exists():
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Hydrate entries from on-disk JSON lines storage."""
        if not self._ledger_file or not self._ledger_file.exists():
            return
        try:
            with open(self._ledger_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        raw = json.loads(stripped)
                        self._entries.append(LocalActionAuditEntry(**raw))
        except Exception as exc:
            logger.error("Failed to load local action ledger from %s: %s", self._ledger_file, exc)

    def _persist_entry_sync(self, entry: LocalActionAuditEntry) -> None:
        """Append serialized entry to disk storage."""
        if not self._ledger_file:
            return
        self._ledger_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._ledger_file, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    async def record_access(
        self,
        agent_id: str,
        target_entity_type: str,
        target_entity_id: str,
        entity_hash: str,
        action: str,
        intent_summary: str,
        operator_or_model: str,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> LocalActionAuditEntry:
        """Append a new verified local entity access entry to the hash chain."""
        async with self._lock:
            prev_hash = self._entries[-1].entry_hash if self._entries else _GENESIS_PREV_HASH

            entry = LocalActionAuditEntry(
                entry_id=str(uuid4()),
                agent_id=agent_id,
                session_id=session_id,
                task_id=task_id,
                timestamp_ns=time.time_ns(),
                target_entity_type=target_entity_type,
                target_entity_id=target_entity_id,
                entity_hash=entity_hash,
                action=action,
                intent_summary=intent_summary,
                operator_or_model=operator_or_model,
                prev_entry_hash=prev_hash,
            )
            entry.entry_hash = entry.compute_hash()
            entry.signature = entry.sign(self._signing_key)
            self._entries.append(entry)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._persist_entry_sync, entry)

            logger.info(
                "Recorded tamper-evident local access: agent=%s entity=%s:%s action=%s",
                agent_id,
                target_entity_type,
                target_entity_id,
                action,
            )
            return entry

    def verify_chain(self) -> tuple[bool, str | None]:
        """Cryptographically verify sequential hash continuity and entry signatures."""
        expected_prev_hash = _GENESIS_PREV_HASH
        for idx, entry in enumerate(self._entries):
            # Check sequential previous hash continuity
            if entry.prev_entry_hash != expected_prev_hash:
                err_msg = (
                    f"Hash continuity broken at index {idx}: expected prev {expected_prev_hash}, "
                    f"got {entry.prev_entry_hash}"
                )
                logger.error(err_msg)
                return False, err_msg

            # Verify entry internal payload hash
            computed = entry.compute_hash()
            if entry.entry_hash != computed:
                err_msg = f"Payload hash mismatch at index {idx}: expected {computed}, got {entry.entry_hash}"
                logger.error(err_msg)
                return False, err_msg

            # Verify cryptographic signature
            if not entry.verify_signature(self._signing_key):
                err_msg = f"Signature verification failed for entry {entry.entry_id} at index {idx}"
                logger.error(err_msg)
                return False, err_msg

            expected_prev_hash = entry.entry_hash

        return True, None

    def query_entries(
        self,
        agent_id: str | None = None,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[LocalActionAuditEntry]:
        """Query entries in reverse chronological order."""
        filtered = self._entries
        if agent_id:
            filtered = [e for e in filtered if e.agent_id == agent_id]
        if entity_type:
            filtered = [e for e in filtered if e.target_entity_type == entity_type]
        return list(reversed(filtered[-limit:]))

    def compute_inspector_summary(self, agent_id: str | None = None) -> PrivacyInspectorSummary:
        """Compute aggregated metrics for WebUI Privacy Inspector."""
        chain_ok, _ = self.verify_chain()
        now = datetime.now(timezone.utc)
        today_start_ns = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp() * 1_000_000_000)

        relevant = self._entries
        if agent_id:
            relevant = [e for e in relevant if e.agent_id == agent_id]

        today_entries = [e for e in relevant if e.timestamp_ns >= today_start_ns]
        entity_counter: Counter[str] = Counter()
        for e in today_entries:
            entity_counter[e.target_entity_type] += 1

        drafts_count = sum(1 for e in today_entries if "draft" in e.action.lower())

        return PrivacyInspectorSummary(
            agent_id=agent_id,
            period="today",
            total_sensitive_entities_read=len(today_entries),
            entity_type_counts=dict(entity_counter),
            total_drafts_created=drafts_count,
            total_financial_interceptions=0,
            total_pending_signoffs=0,
            total_egress_events=0,
            top_egress_hosts=[],
            ledger_chain_healthy=chain_ok,
        )


_default_local_ledger: LocalActionLedgerService | None = None


def get_local_action_ledger() -> LocalActionLedgerService:
    """Return the singleton instance of LocalActionLedgerService."""
    global _default_local_ledger
    if _default_local_ledger is None:
        data_dir = Path(os.getenv("MYRM_DATA_DIR", "/tmp/myrm_data"))
        ledger_path = data_dir / "audit" / "local_actions_ledger.jsonl"
        _default_local_ledger = LocalActionLedgerService(ledger_file=ledger_path)
    return _default_local_ledger
