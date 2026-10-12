"""Stable user- and operator-facing codes for Locked Use failures.

[INPUT]
- UnlockAttemptOutcome from service.py

[OUTPUT]
- locked_use_error_message: English summary for logs, cron output, and support

[POS]
Single place for MYRM_LOCKED_USE_* codes; keep agent system prompts unchanged.
"""

from __future__ import annotations

from app.services.locked_use.service import UnlockAttemptOutcome

_CODE_PREFIX = "MYRM_LOCKED_USE"


def locked_use_error_code(outcome: UnlockAttemptOutcome) -> str:
    return f"{_CODE_PREFIX}_{outcome.value.upper()}"


def locked_use_error_message(outcome: UnlockAttemptOutcome) -> str:
    """Short English explanation suitable for cron transcripts and UI toasts."""
    messages: dict[UnlockAttemptOutcome, str] = {
        UnlockAttemptOutcome.SUCCESS: "Screen unlocked for unattended Computer Use.",
        UnlockAttemptOutcome.ALREADY_UNLOCKED: "Screen was already unlocked.",
        UnlockAttemptOutcome.DEFERRED_USER_PRESENT: "Unattended unlock skipped: someone is using the machine.",
        UnlockAttemptOutcome.SKIPPED_AMBIGUOUS_LOCK_STATE: "Lock state unclear; unlock was not attempted.",
        UnlockAttemptOutcome.NO_PASSWORD: "Locked Use is on but no login password is stored in Keychain.",
        UnlockAttemptOutcome.OSASCRIPT_LAUNCH_FAILED: "Could not run the macOS unlock helper (osascript).",
        UnlockAttemptOutcome.OSASCRIPT_FAILED: "macOS rejected the unlock script.",
        UnlockAttemptOutcome.STILL_LOCKED: "Unlock was attempted but the screen is still locked.",
        UnlockAttemptOutcome.UNVERIFIED_SESSION: "Unlock could not be verified; session state is unknown.",
    }
    return messages.get(outcome, "Unattended screen unlock failed.")
