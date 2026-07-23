"""Ensure enable_web_fetch is derived from agent security at every production callsite."""

from __future__ import annotations

from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_WIRES: frozenset[str] = frozenset(
    {
        "app/services/agent/params/converter.py",
        "app/core/channel_bridge/agent_executor/execute_preamble_agent.py",
        "app/core/cron/adapters/agent_runner.py",
        "app/core/eval/executor.py",
        "app/services/kanban/task_runner.py",
        "app/api/voice/agent_bridge.py",
        "app/api/voice/realtime.py",
    }
)


def test_enable_web_fetch_resolved_at_production_callsites() -> None:
    missing: list[str] = []
    for rel in sorted(REQUIRED_WIRES):
        text = (SERVER_ROOT / rel).read_text(encoding="utf-8")
        if "enable_web_fetch=resolve_enable_web_fetch" not in text:
            missing.append(rel)
        if "resolve_enable_web_fetch" not in text:
            missing.append(f"{rel} (import)")
    assert not missing, f"Missing enable_web_fetch wiring: {missing}"
