"""What the model is told once an ask_question interrupt resumes.

[INPUT]
- myrm_agent_harness.agent.meta_tools.clarification.ask_question::AskQuestionInput (POS: the form the model asked)

[OUTPUT]
- format_ask_question_result: tool result for the resumed ask_question call; every resume without an answer is logged once

[POS]
A skip and the HITL timeout answer the pause they name with an empty value. A plain clarification then continues on the
model's best judgment, but silence is not approval: nothing that waited on the answer may run when it is irreversible or
visible outside the chat. A form flagged ``requires_confirmation`` asked for sign-off before an irreversible or
high-risk operation, so its silence is a refusal.
"""

from __future__ import annotations

import json
import logging

from myrm_agent_harness.agent.meta_tools.clarification.ask_question import AskQuestionInput

logger = logging.getLogger(__name__)

_NO_ANSWER_RESULT = (
    "User did not answer the clarification (skipped or timed out). "
    "Proceed with your best judgment, but silence is not approval: "
    "do not perform irreversible or externally visible actions that were waiting on this answer. "
    "Do not wait for further input."
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
    # One line per silence, so how often questions go unanswered can be counted without recording what was asked.
    logger.info("ask_question resumed without an answer (requires_confirmation=%s)", form.requires_confirmation)
    return _NOT_CONFIRMED_RESULT if form.requires_confirmation else _NO_ANSWER_RESULT
