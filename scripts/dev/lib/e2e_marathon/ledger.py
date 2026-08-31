"""Checkpoint ledger for chrome_e2e marathon (physical 259-node SSOT)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Outcome = Literal[
    "PENDING",
    "PASS",
    "SKIP",
    "FAIL",
    "INFRA_FAIL",
    "INTERRUPTED",
]


@dataclass
class NodeRecord:
    node_id: str
    index: int
    outcome: Outcome
    rc: int | None
    log_path: str | None
    updated_at: float

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "index": self.index,
            "outcome": self.outcome,
            "rc": self.rc,
            "log_path": self.log_path,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> NodeRecord:
        outcome_raw = str(raw.get("outcome", "PENDING"))
        rc_raw = raw.get("rc")
        rc_val = int(rc_raw) if isinstance(rc_raw, int) else None
        log_raw = raw.get("log_path")
        log_path = str(log_raw) if isinstance(log_raw, str) else None
        return NodeRecord(
            node_id=str(raw.get("node_id", "")),
            index=int(raw.get("index", 0)),
            outcome=outcome_raw if outcome_raw in {
                "PENDING",
                "PASS",
                "SKIP",
                "FAIL",
                "INFRA_FAIL",
                "INTERRUPTED",
            } else "PENDING",
            rc=rc_val,
            log_path=log_path,
            updated_at=float(raw.get("updated_at", 0.0)),
        )


@dataclass
class MarathonLedger:
    version: int
    queue: tuple[str, ...]
    nodes: dict[str, NodeRecord]
    started_at: float
    updated_at: float

    def summary(self) -> dict[str, int]:
        counts = {
            "PASS": 0,
            "SKIP": 0,
            "FAIL": 0,
            "INFRA_FAIL": 0,
            "INTERRUPTED": 0,
            "PENDING": 0,
        }
        for record in self.nodes.values():
            counts[record.outcome] = counts.get(record.outcome, 0) + 1
        return counts

    def is_complete(self) -> bool:
        for node_id in self.queue:
            record = self.nodes.get(node_id)
            if record is None or record.outcome not in ("PASS", "SKIP"):
                return False
        return bool(self.queue)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "queue": list(self.queue),
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "nodes": {key: value.to_dict() for key, value in self.nodes.items()},
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> MarathonLedger | None:
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        nodes_raw = raw.get("nodes", {})
        nodes: dict[str, NodeRecord] = {}
        if isinstance(nodes_raw, dict):
            for key, value in nodes_raw.items():
                if isinstance(value, dict):
                    nodes[str(key)] = NodeRecord.from_dict(value)
        queue_raw = raw.get("queue", [])
        queue = tuple(str(item) for item in queue_raw) if isinstance(queue_raw, list) else ()
        return MarathonLedger(
            version=int(raw.get("version", 1)),
            queue=queue,
            nodes=nodes,
            started_at=float(raw.get("started_at", 0.0)),
            updated_at=float(raw.get("updated_at", 0.0)),
        )

    @classmethod
    def create(cls, queue: tuple[str, ...]) -> MarathonLedger:
        now = time.time()
        nodes = {
            node_id: NodeRecord(
                node_id=node_id,
                index=index,
                outcome="PENDING",
                rc=None,
                log_path=None,
                updated_at=now,
            )
            for index, node_id in enumerate(queue, start=1)
        }
        return MarathonLedger(
            version=1,
            queue=queue,
            nodes=nodes,
            started_at=now,
            updated_at=now,
        )

    def set_outcome(
        self,
        node_id: str,
        outcome: Outcome,
        rc: int | None,
        log_path: str | None,
    ) -> None:
        record = self.nodes.get(node_id)
        if record is None:
            return
        self.nodes[node_id] = NodeRecord(
            node_id=record.node_id,
            index=record.index,
            outcome=outcome,
            rc=rc,
            log_path=log_path,
            updated_at=time.time(),
        )
        self.updated_at = time.time()
