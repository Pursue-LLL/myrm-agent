"""A2A structured audit logger.

Records all inbound A2A requests, task state transitions, and webhook deliveries
into a dedicated structured JSONL file for security audit and compliance.

[INPUT]
- event, task_id, agent_id, peer, status, error, details

[OUTPUT]
- record_a2a_audit_event: Asynchronous append to a2a_audit.jsonl

[POS]
Security and compliance audit trail for A2A external agent interactions.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path.home() / ".myrm" / "logs" / "a2a_audit.jsonl"


class A2AAuditLogger:
    """Appends structured audit events to a2a_audit.jsonl."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or _DEFAULT_LOG_PATH

    def _ensure_dir(self) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Failed to create A2A audit log dir: %s", e)

    def log_event(
        self,
        event: str,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        peer: str | None = None,
        status: str | None = None,
        error: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        """Synchronously write an audit event entry."""
        self._ensure_dir()
        record: dict[str, object] = {
            "timestamp": time.time(),
            "event": event,
        }
        if task_id:
            record["task_id"] = task_id
        if agent_id:
            record["agent_id"] = agent_id
        if peer:
            record["peer"] = peer
        if status:
            record["status"] = status
        if error:
            record["error"] = error
        if details:
            record["details"] = details

        try:
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            logger.warning("Failed to write A2A audit log: %s", e)


_default_logger: A2AAuditLogger | None = None


def get_a2a_audit_logger() -> A2AAuditLogger:
    """Return default singleton audit logger."""
    global _default_logger
    if _default_logger is None:
        _default_logger = A2AAuditLogger()
    return _default_logger
