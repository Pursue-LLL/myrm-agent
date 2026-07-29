"""Signoff clarify contract SSOT — deterministic ask_question form for M3 E2E.

[INPUT]
- MYRM_E2E_SIGNOFF_CLARIFY_POOL env (POS: Pool activation gate)
- engineParams.signoffClarifyContract (POS: Per-request contract flag)

[OUTPUT]
- build_signoff_clarify_contract_message: Synthetic AIMessage with ask_question_tool call

[POS]
Pure contract builder for clarify signoff Chrome/API E2E (no LLM dependency).
"""

from __future__ import annotations

import os
import uuid
from typing import Final

from langchain_core.messages import AIMessage

_ASK_QUESTION_TOOL: Final[str] = "ask_question_tool"

SIGNOFF_CLARIFY_FORM_ARGS: Final[dict[str, object]] = {
    "title": "Pick stack",
    "requires_confirmation": False,
    "questions": [
        {
            "id": "stack",
            "prompt": "Which stack?",
            "options": [
                {"id": "a", "label": "Option A"},
                {"id": "b", "label": "Option B"},
            ],
            "allow_multiple": False,
        }
    ],
}


def signoff_clarify_pool_active() -> bool:
    return os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1"


def build_signoff_clarify_ai_message() -> AIMessage:
    """Synthetic first-turn tool call — matches M3 signoff E2E prompt contract."""
    tool_call_id = f"signoff_clarify_{uuid.uuid4().hex[:12]}"
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": tool_call_id,
                "name": _ASK_QUESTION_TOOL,
                "args": dict(SIGNOFF_CLARIFY_FORM_ARGS),
            }
        ],
    )
