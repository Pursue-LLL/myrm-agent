"""Guardrail: production GeneralAgentParams entry points must apply the response-locale suffix.

GeneralAgentParams constructor allowlist is guarded separately by
``tests/core/agents/test_general_agent_params_callsites_guard.py``.

Ten paths (Web, Channel, Cron, Kanban, Eval, Voice×3, Subagent, Goal stream).
"""

from __future__ import annotations

from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[4]

RESPONSE_LOCALE_SUFFIX_REQUIRED: frozenset[str] = frozenset(
    {
        "app/services/agent/params/conversion/profile_apply.py",
        "app/core/channel_bridge/agent_executor/execute_preamble/instructions.py",
        "app/core/cron/adapters/agent_runner/profile.py",
        "app/services/kanban/task_runner/runner.py",
        "app/core/eval/executor.py",
        "app/api/voice/agent_bridge/params.py",
        "app/api/voice/realtime.py",
        "app/api/voice/gemini_live.py",
        "app/ai_agents/custom_agent_factory.py",
        "app/services/agent/goals/unattended/trigger.py",
    }
)

# The communication-style block is rendered only for the IM session-level ``/personality`` choice. An agent's own style
# is ordinary system-prompt text, so no other runtime path may render a style block.
STYLE_BLOCK_RENDERER_FILES: frozenset[str] = frozenset(
    {
        "app/ai_agents/personality_templates.py",
        "app/core/channel_bridge/agent_executor/execute_preamble/instructions.py",
    }
)
# The data-fix migration freezes its own copy of the block text; no other file may carry the block heading.
STYLE_BLOCK_HEADING_FILES: frozenset[str] = frozenset(
    {
        "app/ai_agents/personality_templates.py",
        "app/database/personality_style_merge.py",
    }
)


def _files_containing(needle: str) -> frozenset[str]:
    return frozenset(
        path.relative_to(SERVER_ROOT).as_posix()
        for path in (SERVER_ROOT / "app").rglob("*.py")
        if needle in path.read_text(encoding="utf-8")
    )


def test_response_locale_suffix_applied_at_entry_points() -> None:
    missing: list[str] = []
    for rel in sorted(RESPONSE_LOCALE_SUFFIX_REQUIRED):
        text = (SERVER_ROOT / rel).read_text(encoding="utf-8")
        if "apply_response_locale_suffix" not in text:
            missing.append(rel)
    assert not missing, (
        "Entry points missing apply_response_locale_suffix:\n"
        + "\n".join(f"  - {rel}" for rel in missing)
        + "\nWire response_locale_suffix or update RESPONSE_LOCALE_SUFFIX_REQUIRED."
    )


def test_style_block_is_rendered_only_for_the_im_session_choice() -> None:
    assert _files_containing("render_personality_block") == STYLE_BLOCK_RENDERER_FILES


def test_style_block_heading_has_no_stray_copy() -> None:
    assert _files_containing("**Communication Style**") == STYLE_BLOCK_HEADING_FILES
