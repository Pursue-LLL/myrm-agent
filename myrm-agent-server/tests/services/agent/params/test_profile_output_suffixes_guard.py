"""Guardrail: production GeneralAgentParams entry points must apply profile output suffixes.

GeneralAgentParams constructor allowlist is guarded separately by
``tests/core/agents/test_general_agent_params_callsites_guard.py``.

Ten paths (Web, Channel, Cron, Kanban, Eval, Voice×3, Subagent, Goal stream).
"""

from __future__ import annotations

from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[4]

PROFILE_OUTPUT_SUFFIX_REQUIRED: frozenset[str] = frozenset(
    {
        "app/services/agent/params/converter.py",
        "app/core/channel_bridge/agent_executor/execute_preamble_instructions.py",
        "app/core/cron/adapters/agent_runner.py",
        "app/services/kanban/task_runner.py",
        "app/core/eval/executor.py",
        "app/api/voice/agent_bridge.py",
        "app/api/voice/realtime.py",
        "app/api/voice/gemini_live.py",
        "app/ai_agents/custom_agent_factory.py",
        "app/services/agent/goal_stream_trigger.py",
    }
)


def test_profile_output_suffix_applied_at_entry_points() -> None:
    missing: list[str] = []
    for rel in sorted(PROFILE_OUTPUT_SUFFIX_REQUIRED):
        text = (SERVER_ROOT / rel).read_text(encoding="utf-8")
        if "apply_profile_output_suffixes" not in text:
            missing.append(rel)
    assert not missing, (
        "Entry points missing apply_profile_output_suffixes:\n"
        + "\n".join(f"  - {rel}" for rel in missing)
        + "\nWire profile_output_suffixes or update PROFILE_OUTPUT_SUFFIX_REQUIRED."
    )
