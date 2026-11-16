"""Page origin, prompts and API wait budget of the clarify Skip live Chrome E2E.

[INPUT]
- dev_gate.contract::clarify_skip_api_wait_sec (POS: Dev Gate contract SSOT for Chrome MCP E2E orchestration: error tokens, parallel caps and timeout budgets)
- e2e_core.dev_ports::shared_ui_base (POS: Default ports of the user, shared dev and isolated stacks — SSOT)

[OUTPUT]
- BASE_URL: WebUI origin the live test opens
- E2E_PROMPT / E2E_PROMPT_SIGNOFF / E2E_NUDGE_PROMPT: prompts that make the model open one clarification card
- E2E_SKIP_RESUME_QUERY: query sent when the server rejects a skip resume for lack of a user query
- skip_api_wait_sec(): wait budget in seconds (`CLARIFY_SKIP_API_WAIT_SEC` overrides the contract value)

[POS]
Single source for the clarify Skip E2E's page origin, prompts and wait budget.
"""

from __future__ import annotations

import os

from dev_gate.contract import clarify_skip_api_wait_sec
from e2e_core.dev_ports import shared_ui_base

BASE_URL = os.getenv("E2E_UI_BASE", shared_ui_base()).rstrip("/")


def skip_api_wait_sec() -> float:
    override = os.environ.get("CLARIFY_SKIP_API_WAIT_SEC", "").strip()
    if override:
        return float(override)
    return float(clarify_skip_api_wait_sec())


# WebUI path: avoid CRITICAL/MUST phrasing for dev chrome_e2e (MiniMax-M3 injection risk).
# E2E_SIGNOFF=1 uses E2E_PROMPT_SIGNOFF with CRITICAL prefix for fail-fast tool call.
E2E_PROMPT = (
    "Before doing anything else, use ask_question_tool exactly once to ask which stack I prefer "
    "for a small demo project. "
    'Use title "Pick stack", one question id "stack" prompt "Which stack?", '
    'options id "a" label "Option A" and id "b" label "Option B", requires_confirmation false. '
    "Do not use bash, write_file, or other tools. "
    "If I skip without answering, reply with exactly: DONE-SKIPPED"
)

# E2E_SIGNOFF=1: align with API E2E prompt that reliably triggers ask_question_tool first.
E2E_PROMPT_SIGNOFF = (
    "CRITICAL: Your very first action MUST be a single ask_question_tool call — no text reply before it. "
    "You MUST call ask_question_tool exactly once before any other action. "
    'Use title "Pick stack". Ask one question with id "stack" and prompt '
    '"Which stack?" with two options: id "a" label "Option A", id "b" label "Option B". '
    "Set requires_confirmation to false. "
    "Do not use bash, write_file, or any other tools. "
    "If I skip without answering, reply with exactly: DONE-SKIPPED"
)

E2E_NUDGE_PROMPT = (
    "Please open the structured clarification form now: ask_question_tool once, "
    'title "Pick stack", question id "stack" prompt "Which stack?", '
    'options "a" Option A and "b" Option B. If I skip, reply DONE-SKIPPED.'
)
E2E_SKIP_RESUME_QUERY = "Continue after skip."
