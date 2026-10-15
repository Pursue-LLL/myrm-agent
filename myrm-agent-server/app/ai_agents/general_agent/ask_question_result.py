"""What the model is told once an ask_question interrupt resumes.

[INPUT]
- myrm_agent_harness.agent.meta_tools.clarification.ask_question::AskQuestionInput (POS: the form the model asked)

[OUTPUT]
- format_ask_question_result: tool result for the resumed ask_question call

[POS]
The user's skip and the HITL timeout both resume the interrupt with an empty value. A plain clarification may
then continue on the model's best judgment, but a form flagged ``requires_confirmation`` asked for sign-off
before an irreversible or high-risk operation, so silence must never read as consent.
"""

from __future__ import annotations

import json

from myrm_agent_harness.agent.meta_tools.clarification.ask_question import AskQuestionInput

_NO_ANSWER_RESULT = (
    "User did not answer the clarification (skipped or timed out). "
    "Proceed with your best judgment; do not wait for further input."
)

_NOT_CONFIRMED_RESULT = (
    "The user did not confirm (skipped or timed out), so the operation is NOT approved. "
    "Do not perform it and do not ask again; tell the user it was not done because confirmation was not received, "
    "and continue only with work that does not depend on it."
)


def format_ask_question_result(form: AskQuestionInput, response: object) -> str:
    """Render the resume value of an ask_question interrupt as the tool result."""
    if response:
        return json.dumps(response, ensure_ascii=False)
    return _NOT_CONFIRMED_RESULT if form.requires_confirmation else _NO_ANSWER_RESULT
