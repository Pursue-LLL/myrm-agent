"""Test doubles shared by the CLI session tests."""

from __future__ import annotations

from myrm_agent_harness.toolkits.acp.types import CliSessionRecord


class RecordingStore:
    """In-memory ``CliSessionStore`` that logs every operation and can be told to fail one."""

    def __init__(self) -> None:
        self.records: dict[str, CliSessionRecord] = {}
        self.ops: list[tuple[str, str]] = []
        self.failing: set[str] = set()

    async def load(self, session_id: str) -> CliSessionRecord | None:
        self._enter("load", session_id)
        return self.records.get(session_id)

    async def save(self, session_id: str, record: CliSessionRecord) -> None:
        self._enter("save", session_id)
        self.records[session_id] = record

    async def delete(self, session_id: str) -> None:
        self._enter("delete", session_id)
        self.records.pop(session_id, None)

    def _enter(self, op: str, session_id: str) -> None:
        self.ops.append((op, session_id))
        if op in self.failing:
            raise RuntimeError(f"{op} failed")
