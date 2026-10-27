"""How a refusal reads to the model: who refused, and what to do next.

[INPUT]
- (none — pure text)

[OUTPUT]
- DenialCause: who or what refused the call (a policy, a person, an approval timeout)
- rejection_message: the ToolMessage text for a call a person did not approve
- denial_hint: the ``[System: ...]`` note appended to a refusal, escalated once a denial threshold is breached

[POS]
Text only. The counters and thresholds live in helpers.py and the decision branches in _batch_decisions.py.
A refusal that blames a "security block" for a person's "no", or that tells the model a person declined when
nobody answered, makes the model argue with the wrong party, so the cause picks the wording.
"""

from __future__ import annotations

from enum import StrEnum


class DenialCause(StrEnum):
    """Who or what refused a tool call."""

    POLICY = "policy"
    USER = "user"
    TIMEOUT = "timeout"


_HINTS = {
    DenialCause.POLICY: (
        "\n\n[System: This action was denied. "
        "Find a safer alternative approach to achieve the user's goal. "
        "Do NOT attempt to circumvent or route around the security block.]"
    ),
    DenialCause.USER: (
        "\n\n[System: The user declined this action. "
        "Do not run it again or look for a way around the refusal. "
        "If their reason allows a different approach, take it; otherwise ask them how to proceed.]"
    ),
    DenialCause.TIMEOUT: (
        "\n\n[System: The user did not answer in time. "
        "Do not run this action again on your own. "
        "Tell the user what you were trying to do and wait for their reply.]"
    ),
}

_TIMEOUT_MESSAGE = "Action not run: the approval request timed out and the user did not answer."

_AUTO_MODE_SUSPENDED = "Auto-mode is being suspended — all subsequent actions will require explicit human approval."
_ATTENDED_ESCALATION = {
    "total": (
        "{count} total denials in this session (threshold: {threshold}). "
        f"{_AUTO_MODE_SUSPENDED} Explain to the user what happened and ask for guidance."
    ),
    "consecutive": (
        "{count} consecutive denials (threshold: {threshold}). "
        f"{_AUTO_MODE_SUSPENDED} Stop and explain to the user what you were trying to do."
    ),
}
_UNATTENDED_ESCALATION = (
    "{count} {breach} denials for this scheduled job (threshold: {threshold}). "
    "Do not retry the denied actions. "
    "Finish whatever does not need them and state in your final reply what was blocked and why."
)


def rejection_message(feedback: str, *, timed_out: bool) -> str:
    """The ToolMessage text for a call a person did not approve: their reason, or the fact that nobody answered."""
    return _TIMEOUT_MESSAGE if timed_out else f"Action rejected by user: {feedback}"


def denial_hint(cause: DenialCause, breach: str, count: int, threshold: int, *, unattended: bool) -> str:
    """The note appended to a refusal.

    *breach* is ``"none"``, ``"consecutive"`` or ``"total"``; *count* and *threshold* describe the breached counter.
    Past a threshold the note stops the model instead of asking it to try again. An unattended run (a scheduled
    job) has nobody to ask, so its note tells the model to finish what it can and report the rest.
    """
    if breach == "none":
        return _HINTS[cause]
    template = _UNATTENDED_ESCALATION if unattended else _ATTENDED_ESCALATION[breach]
    return "\n\n[System: " + template.format(count=count, breach=breach, threshold=threshold) + "]"
