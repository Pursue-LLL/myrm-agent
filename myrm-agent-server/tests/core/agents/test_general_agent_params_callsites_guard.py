"""Guardrail: every GeneralAgentParams direct constructor and `model_validate` site under `app/` must match allowlist.

When adding a new construction site, update EXPECTED_* below and verify
`auto_restore_domains`, `enable_browser`, `enable_render_ui`, `enable_web_fetch`, and related ResolvedAgentProfile fields
are passed consistently (Web / Channel / Cron / Eval / Voice parity).
"""

from __future__ import annotations

import re
from pathlib import Path

# tests/core/agents/<this>.py -> repo root is parents[3]
SERVER_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = SERVER_ROOT / "app"

EXPECTED_GENERAL_AGENT_PARAMS_DIRECT: frozenset[str] = frozenset(
    {
        "app/api/voice/agent_bridge.py",
        "app/api/voice/realtime.py",
        "app/services/agent/goal_stream_trigger.py",
        "app/services/agent/params/converter.py",
        "app/services/agent/stream_session/memory_brief.py",
        "app/core/channel_bridge/agent_executor/execute_preamble_agent.py",
        "app/core/channel_bridge/agent_executor/execute_preamble_types.py",
        "app/core/cron/adapters/agent_runner.py",
        "app/core/eval/executor.py",
        "app/services/kanban/task_runner.py",
    }
)

EXPECTED_GENERAL_AGENT_PARAMS_MODEL_VALIDATE: frozenset[str] = frozenset(
    {
        "app/lifecycle/system.py",
    }
)

# Production callsites that construct GeneralAgentParams must pass ``locale=`` for
# harness tool description SSOT (memory/web_search). Eval is intentionally excluded.
LOCALE_REQUIRED_GENERAL_AGENT_PARAMS_CALLSITES: frozenset[str] = frozenset(
    {
        "app/api/voice/agent_bridge.py",
        "app/api/voice/realtime.py",
        "app/core/channel_bridge/agent_executor/execute_preamble_agent.py",
        "app/core/cron/adapters/agent_runner.py",
        "app/services/agent/goal_stream_trigger.py",
        "app/services/agent/params/converter.py",
        "app/services/kanban/task_runner.py",
    }
)

LOCALE_EXCLUDED_GENERAL_AGENT_PARAMS_CALLSITES: frozenset[str] = frozenset(
    {
        "app/core/eval/executor.py",
    }
)


def _discover_callsites() -> tuple[set[str], set[str]]:
    direct: set[str] = set()
    model_validate: set[str] = set()
    for path in APP_ROOT.rglob("*.py"):
        rel = path.relative_to(SERVER_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "GeneralAgentParams.model_validate" in line:
                model_validate.add(rel)
                continue
            if re.search(r"\bGeneralAgentParams\s*\(", line):
                if stripped.startswith("class ") and "GeneralAgentParams" in stripped:
                    continue
                direct.add(rel)
    return direct, model_validate


def test_general_agent_params_direct_callsites_match_allowlist() -> None:
    direct, _ = _discover_callsites()
    assert direct == EXPECTED_GENERAL_AGENT_PARAMS_DIRECT, (
        "GeneralAgentParams( callsites under app/ changed.\n"
        f"Extra: {sorted(direct - EXPECTED_GENERAL_AGENT_PARAMS_DIRECT)}\n"
        f"Missing: {sorted(EXPECTED_GENERAL_AGENT_PARAMS_DIRECT - direct)}\n"
        f"Update EXPECTED_* in {Path(__file__).name} after reviewing ResolvedAgentProfile parity."
    )


def test_general_agent_params_model_validate_callsites_match_allowlist() -> None:
    _, model_validate = _discover_callsites()
    assert model_validate == EXPECTED_GENERAL_AGENT_PARAMS_MODEL_VALIDATE, (
        "GeneralAgentParams.model_validate callsites under app/ changed.\n"
        f"Got: {sorted(model_validate)}\n"
        f"Expected: {sorted(EXPECTED_GENERAL_AGENT_PARAMS_MODEL_VALIDATE)}\n"
        f"Update EXPECTED_* in {Path(__file__).name}."
    )


def test_production_general_agent_params_pass_locale() -> None:
    missing: list[str] = []
    for rel in sorted(LOCALE_REQUIRED_GENERAL_AGENT_PARAMS_CALLSITES):
        path = SERVER_ROOT / rel
        text = path.read_text(encoding="utf-8")
        idx = text.find("GeneralAgentParams(")
        assert idx != -1, f"{rel} has no GeneralAgentParams("
        snippet = text[idx : idx + 5000]
        if "locale=" not in snippet:
            missing.append(rel)
    assert not missing, (
        "GeneralAgentParams construction missing locale= in:\n"
        + "\n".join(f"  - {rel}" for rel in missing)
        + f"\nUpdate LOCALE_REQUIRED_* in {Path(__file__).name} or pass locale=."
    )
    assert LOCALE_EXCLUDED_GENERAL_AGENT_PARAMS_CALLSITES.isdisjoint(
        LOCALE_REQUIRED_GENERAL_AGENT_PARAMS_CALLSITES
    )
