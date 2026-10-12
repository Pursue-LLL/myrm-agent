"""Egress data footprint ledger service.

[POS]
Maintains immutable records of outbound network transmissions initiated by agents.
Enforces the honest distinction between memory forgetting (reversible)
and network egress facts (irreversible, auditable-only).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import Counter
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.schemas.local_action_audit import EgressFootprintReceipt

logger = logging.getLogger(__name__)


class EgressFootprintLedgerService:
    """Manages append-only egress receipts and aggregates data destination footprints."""

    def __init__(self, ledger_file: Path | None = None) -> None:
        self._ledger_file: Path | None = ledger_file
        self._receipts: list[EgressFootprintReceipt] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        if self._ledger_file and self._ledger_file.exists():
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Hydrate egress receipts from on-disk JSON lines."""
        if not self._ledger_file or not self._ledger_file.exists():
            return
        try:
            with open(self._ledger_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        data = json.loads(stripped)
                        self._receipts.append(EgressFootprintReceipt(**data))
        except Exception as exc:
            logger.error("Failed to load egress footprint ledger from %s: %s", self._ledger_file, exc)

    def _persist_receipt_sync(self, receipt: EgressFootprintReceipt) -> None:
        """Append receipt to local storage."""
        if not self._ledger_file:
            return
        self._ledger_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._ledger_file, "a", encoding="utf-8") as f:
            f.write(receipt.model_dump_json() + "\n")

    async def record_egress(
        self,
        agent_id: str,
        target_host: str,
        target_url: str,
        content_summary: str,
        method: str = "POST",
        sensitivity_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "HIGH",
        taint_tags: list[str] | None = None,
        credential_redacted: bool = False,
        approved_by_human: bool = False,
        approval_id: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> EgressFootprintReceipt:
        """Record an outbound transmission fact into the immutable footprint ledger."""
        async with self._lock:
            receipt = EgressFootprintReceipt(
                receipt_id=str(uuid4()),
                agent_id=agent_id,
                session_id=session_id,
                task_id=task_id,
                timestamp=time.time(),
                target_host=target_host,
                target_url=target_url,
                method=method,
                content_summary=content_summary,
                sensitivity_level=sensitivity_level,
                taint_tags=taint_tags or [],
                credential_redacted=credential_redacted,
                approved_by_human=approved_by_human,
                approval_id=approval_id,
                is_revocable=False,
            )
            self._receipts.append(receipt)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._persist_receipt_sync, receipt)

            logger.info(
                "Recorded egress footprint: agent=%s host=%s sensitivity=%s human_approved=%s",
                agent_id,
                target_host,
                sensitivity_level,
                approved_by_human,
            )
            return receipt

    def query_footprints(
        self,
        agent_id: str | None = None,
        session_id: str | None = None,
        target_host: str | None = None,
        limit: int = 100,
    ) -> list[EgressFootprintReceipt]:
        """Query egress receipts in reverse chronological order."""
        filtered = self._receipts
        if agent_id:
            filtered = [r for r in filtered if r.agent_id == agent_id]
        if session_id:
            filtered = [r for r in filtered if r.session_id == session_id]
        if target_host:
            filtered = [r for r in filtered if r.target_host == target_host]
        return list(reversed(filtered[-limit:]))

    def get_top_hosts(self, agent_id: str | None = None, limit: int = 5) -> list[dict[str, str | int]]:
        """Compute the most frequently contacted external hosts."""
        relevant = self._receipts
        if agent_id:
            relevant = [r for r in relevant if r.agent_id == agent_id]

        host_counts: Counter[str] = Counter(r.target_host for r in relevant)
        return [{"host": host, "count": count} for host, count in host_counts.most_common(limit)]

    def export_all(self, agent_id: str | None = None) -> list[dict[str, object]]:
        """Export serialized footprint data for audit dossiers."""
        relevant = self._receipts
        if agent_id:
            relevant = [r for r in relevant if r.agent_id == agent_id]
        return [r.model_dump() for r in relevant]


_default_egress_ledger: EgressFootprintLedgerService | None = None


def get_egress_footprint_ledger() -> EgressFootprintLedgerService:
    """Return the singleton instance of EgressFootprintLedgerService."""
    global _default_egress_ledger
    if _default_egress_ledger is None:
        data_dir = Path(os.getenv("MYRM_DATA_DIR", "/tmp/myrm_data"))
        ledger_path = data_dir / "audit" / "egress_footprints.jsonl"
        _default_egress_ledger = EgressFootprintLedgerService(ledger_file=ledger_path)
    return _default_egress_ledger
