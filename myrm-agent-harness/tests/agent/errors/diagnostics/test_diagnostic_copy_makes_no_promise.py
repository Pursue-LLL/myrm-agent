"""A failure card never promises what the system does next.

The card is built after the turn's own recovery (in-turn retries, model failover) has ended or did not apply, so a line
such as "retrying automatically" is false in every state the card can appear in. Two entries are exempt because the
engine emits them at the moment the action happens, as a non-fatal step: a cut-off tool call that is being retried and a
truncated response that is being continued. Only the English catalog is scanned: it is the one every other catalog
translates, and a promise cannot be matched reliably across six languages.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

from myrm_agent_harness.agent.errors.diagnostics.i18n import manager as manager_module

_ENGLISH_CATALOG = Path(manager_module.__file__).parent / "locales" / "en.json"
_COPY_SUFFIXES = ("_user_message", "_resolution_steps", "_wait_step")
_EMITTED_WHILE_THE_ACTION_RUNS = frozenset({"tool_call_retry_user_message", "text_continuation_user_message"})

# "so overloads switch over automatically" is a setup hint that names its condition, not a promise, so it is not matched.
_PROMISE = re.compile(r"\bretrying\b|\bautomatic retry\b|\bautomatically (?:retry|switch|continu)", re.IGNORECASE)


def _english_copy() -> Iterator[tuple[str, str]]:
    bundle: dict[str, str | list[str]] = json.loads(_ENGLISH_CATALOG.read_text(encoding="utf-8"))
    for key, value in bundle.items():
        if key.endswith(_COPY_SUFFIXES):
            for text in value if isinstance(value, list) else [value]:
                yield key, text


def test_failure_cards_make_no_promise_about_what_the_system_does_next() -> None:
    offenders = [
        f"{key}: {text}"
        for key, text in _english_copy()
        if key not in _EMITTED_WHILE_THE_ACTION_RUNS and _PROMISE.search(text)
    ]

    assert offenders == []


def test_the_exemptions_are_exactly_the_entries_that_would_otherwise_be_flagged() -> None:
    flagged = {key for key, text in _english_copy() if _PROMISE.search(text)}

    assert flagged == _EMITTED_WHILE_THE_ACTION_RUNS


def test_the_scan_catches_a_promise_and_lets_a_conditional_setup_hint_pass() -> None:
    assert _PROMISE.search("TLS handshake interrupted — retrying automatically")
    assert _PROMISE.search("No action needed if the automatic retry succeeds")
    assert _PROMISE.search("System is automatically switching to fallback model")
    assert not _PROMISE.search("Set a Fallback Model in Settings so rate limits switch over automatically")
    assert not _PROMISE.search("Send your message again")
