"""Spending Ledger Models and Tamper-Evident Storage for Agent Commerce.

[INPUT]
- json, os, threading, time: Python 标准库
- datetime::datetime, timezone
- pydantic::BaseModel, Field
- typing::Literal

[OUTPUT]
- SpendingLedgerEntry: 单笔消费流水明细模型
- SpendingLedgerStore: 线程安全且本地持久化的消费流水账本存储
- get_spending_ledger_store: 账本单例访问器

[POS]
Server-level transactional commerce ledger in app/commerce/.
Provides audit trail and receipt verification for autonomous agent spending.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LedgerStatus = Literal["reserved", "committed", "refunded", "rejected"]


class SpendingLedgerEntry(BaseModel):
    """Immutable audit record for an autonomous agent commerce expenditure."""

    entry_id: str = Field(description="Unique ledger entry identifier")
    lease_id: str = Field(description="Associated SpendGovernor lease ID")
    session_id: str = Field(default="global", description="Agent session identifier")
    task_id: str | None = Field(default=None, description="Optional associated task ID")
    merchant_domain: str = Field(description="Normalized target merchant domain")
    amount_cents: int = Field(gt=0, description="Transaction amount in integer USD Cents")
    currency: str = Field(default="USD", description="Currency ISO code")
    status: LedgerStatus = Field(default="reserved", description="Current lifecycle state")
    action_digest: str | None = Field(default=None, description="HMAC-SHA256 signature of the spend action")
    entry_hash: str | None = Field(default=None, description="Cryptographic chained hash from SpendGovernor")
    idempotency_key: str = Field(default="", description="Idempotency key to prevent double charging")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SpendingLedgerStore:
    """Thread-safe persistent store for spending ledger records."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        if storage_path is None:
            base_dir = os.environ.get("MYRM_DATA_DIR") or os.path.expanduser("~/.myrm")
            storage_path = Path(base_dir) / "spending_ledger.json"
        self._path: Path = Path(storage_path)
        self._entries: list[SpendingLedgerEntry] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load records from local persistent storage."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                raw_data = json.load(f)
            if isinstance(raw_data, list):
                self._entries = [SpendingLedgerEntry.model_validate(item) for item in raw_data]
        except Exception as exc:
            logger.warning("Failed loading spending ledger from %s: %s", self._path, exc)

    def _persist(self) -> None:
        """Write records atomically to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".tmp")
            data = [entry.model_dump() for entry in self._entries]
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self._path)
        except Exception as exc:
            logger.error("Failed persisting spending ledger to %s: %s", self._path, exc)

    def record_entry(self, entry: SpendingLedgerEntry) -> SpendingLedgerEntry:
        """Append a new spending ledger entry."""
        with self._lock:
            # Check duplicate entry_id
            for idx, existing in enumerate(self._entries):
                if existing.entry_id == entry.entry_id:
                    self._entries[idx] = entry
                    self._persist()
                    return entry
            self._entries.insert(0, entry)
            self._persist()
            return entry

    def update_status(
        self,
        lease_id: str,
        status: LedgerStatus,
        entry_hash: str | None = None,
        action_digest: str | None = None,
    ) -> SpendingLedgerEntry | None:
        """Update transaction status and cryptographic receipt hash for a lease."""
        with self._lock:
            for entry in self._entries:
                if entry.lease_id == lease_id:
                    entry.status = status
                    entry.updated_at = datetime.now(timezone.utc).isoformat()
                    if entry_hash is not None:
                        entry.entry_hash = entry_hash
                    if action_digest is not None:
                        entry.action_digest = action_digest
                    self._persist()
                    return entry
        return None

    def list_entries(
        self,
        session_id: str | None = None,
        status: LedgerStatus | None = None,
        limit: int = 50,
    ) -> list[SpendingLedgerEntry]:
        """Query entries with optional filtering and pagination."""
        with self._lock:
            results: list[SpendingLedgerEntry] = []
            for entry in self._entries:
                if session_id and entry.session_id != session_id:
                    continue
                if status and entry.status != status:
                    continue
                results.append(entry)
                if len(results) >= limit:
                    break
            return results

    def get_committed_cents_since(self, since_iso_or_timestamp: float | str) -> int:
        """Calculate total committed cents since a given timestamp or ISO time."""
        since_iso: str
        if isinstance(since_iso_or_timestamp, (int, float)):
            since_iso = datetime.fromtimestamp(since_iso_or_timestamp, tz=timezone.utc).isoformat()
        else:
            since_iso = since_iso_or_timestamp

        with self._lock:
            total = 0
            for entry in self._entries:
                if entry.status == "committed" and entry.updated_at >= since_iso:
                    total += entry.amount_cents
            return total

    def get_entry(self, entry_id_or_lease_id: str) -> SpendingLedgerEntry | None:
        """Look up an entry by entry_id or lease_id."""
        with self._lock:
            for entry in self._entries:
                if entry.entry_id == entry_id_or_lease_id or entry.lease_id == entry_id_or_lease_id:
                    return entry
        return None


_GLOBAL_LEDGER_STORE: SpendingLedgerStore | None = None
_STORE_LOCK = threading.Lock()


def get_spending_ledger_store(storage_path: str | Path | None = None) -> SpendingLedgerStore:
    """Get or initialize singleton spending ledger store."""
    global _GLOBAL_LEDGER_STORE
    with _STORE_LOCK:
        if _GLOBAL_LEDGER_STORE is None or storage_path is not None:
            _GLOBAL_LEDGER_STORE = SpendingLedgerStore(storage_path=storage_path)
        return _GLOBAL_LEDGER_STORE
