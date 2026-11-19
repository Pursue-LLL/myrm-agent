"""Guardrail: the communication-style block has exactly one renderer and one frozen copy.

GeneralAgentParams constructor allowlist is guarded separately by
``tests/core/agents/test_general_agent_params_callsites_guard.py``.
"""

from __future__ import annotations

from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[4]

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


def test_style_block_is_rendered_only_for_the_im_session_choice() -> None:
    assert _files_containing("render_personality_block") == STYLE_BLOCK_RENDERER_FILES


def test_style_block_heading_has_no_stray_copy() -> None:
    assert _files_containing("**Communication Style**") == STYLE_BLOCK_HEADING_FILES
