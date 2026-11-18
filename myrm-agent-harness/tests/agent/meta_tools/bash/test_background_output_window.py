"""The window a read of a background job's output shows: how it is cut to a size budget and how its secrets are masked."""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.output_window import (
    WINDOW_MAX_CHARS,
    cap_window,
    redact_window,
)
from myrm_agent_harness.agent.security.redact import redact_sensitive_text
from tests.agent.meta_tools.bash.secret_shapes import KEY_KINDS, key_block, key_body

_BODY = key_body(4)


def _leaks_body(lines: list[str]) -> bool:
    text = "\n".join(lines)
    return any(part in text for part in _BODY)


def test_a_window_within_the_budget_is_kept_whole() -> None:
    lines = [f"line {i}" for i in range(50)]

    assert cap_window(lines) == (lines, False)


def test_a_window_over_the_budget_keeps_the_newest_lines_and_reports_the_cut() -> None:
    lines = [f"{i:04d} " + "x" * 995 for i in range(200)]

    kept, cut = cap_window(lines)

    assert cut is True
    assert kept == lines[-len(kept) :]
    assert 0 < len(kept) < len(lines)
    assert sum(len(line) + 1 for line in kept) <= WINDOW_MAX_CHARS
    # One more line of the same size would not fit.
    assert sum(len(line) + 1 for line in lines[-len(kept) - 1 :]) > WINDOW_MAX_CHARS


def test_a_window_that_fills_the_budget_exactly_is_not_cut() -> None:
    half = WINDOW_MAX_CHARS // 2 - 1
    lines = ["a" * half, "b" * half]

    assert cap_window(lines) == (lines, False)
    assert cap_window(["c", *lines])[1] is True


def test_the_newest_line_is_kept_however_long() -> None:
    huge = "z" * (3 * WINDOW_MAX_CHARS)

    assert cap_window([huge]) == ([huge], False)
    assert cap_window(["before", huge]) == ([huge], True)


def test_an_empty_window_stays_empty() -> None:
    assert cap_window([]) == ([], False)
    assert redact_window([]) == []


def test_a_secret_inside_one_line_is_masked_and_the_rest_of_the_line_is_not() -> None:
    masked = redact_window(["POST body: password=hunter2hunter2&lang=en", "plain line"])

    assert "hunter2hunter2" not in masked[0]
    assert "lang=en" in masked[0]
    assert masked[1] == "plain line"


@pytest.mark.parametrize("kind", KEY_KINDS)
def test_a_key_block_split_over_lines_is_masked_as_a_whole(kind: str) -> None:
    lines = ["before", *key_block(kind, body=_BODY), "after"]

    # A line alone is no key block: this is why the window is masked again as one text.
    assert _leaks_body([redact_sensitive_text(line) for line in lines])

    masked = redact_window(lines)

    assert not _leaks_body(masked)
    assert masked[0] == "before"
    assert masked[-1] == "after"
    assert f"-----BEGIN {kind}-----" in masked
    assert f"-----END {kind}-----" in masked


def test_a_json_pair_split_over_two_lines_is_masked() -> None:
    lines = ["{", '  "client_secret":', '    "s3cr3t-value-0123456789"', "}"]

    assert "s3cr3t-value-0123456789" in "\n".join(redact_sensitive_text(line) for line in lines)
    assert "s3cr3t-value-0123456789" not in "\n".join(redact_window(lines))


def test_the_lines_around_a_masked_block_come_back_unchanged() -> None:
    before = [f"building {i}" for i in range(5)]
    after = [f"done {i}" for i in range(5)]

    masked = redact_window([*before, *key_block(body=_BODY), *after])

    assert masked[:5] == before
    assert masked[-5:] == after


def test_the_most_openers_a_window_can_hold_are_masked_within_two_seconds() -> None:
    """A key block that never closes is the worst case of the whole-text pass; the window cap bounds what it scans.

    CPU time, not wall time: the bound is on the work a read does, whatever else the machine is running.
    """
    window, cut = cap_window(["-----BEGIN RSA PRIVATE KEY-----"] * 2_420)
    assert cut is True
    assert len(window) > 2_000

    started = time.process_time()
    masked = redact_window(window)
    elapsed = time.process_time() - started

    assert len(masked) == len(window)
    assert elapsed < 2.0, f"masking {len(window)} openers took {elapsed:.2f} s of CPU"


def test_a_full_window_of_long_lines_is_masked_within_two_seconds() -> None:
    """The costliest content measured: 64 KiB of long lines made of one repeated character."""
    window, cut = cap_window(["-----BEGIN RSA PRIVATE KEY-----" + "Z" * 300 for _ in range(200)])
    assert cut is True
    assert sum(len(line) + 1 for line in window) > WINDOW_MAX_CHARS - 1_000

    started = time.process_time()
    redact_window(window)
    elapsed = time.process_time() - started

    assert elapsed < 2.0, f"masking a {WINDOW_MAX_CHARS}-character window took {elapsed:.2f} s of CPU"
