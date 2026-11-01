"""Assertion that a client's wait limit is a real bound.

[INPUT]
(none)

[OUTPUT]
- assert_bounded_wait: the timeout a client was given is a positive number of seconds, at most ``limit``

[POS]
Server pytest-only helper for the clients that must not wait on a silent server forever. Comparing the value with the
constant that produced it passes when both become ``None``; this fails.
"""

from __future__ import annotations

# A mail server that answers nothing is given at most this long; the clients under test use 10 to 30 seconds.
_DEFAULT_LIMIT_SECONDS = 60


def assert_bounded_wait(timeout: object, *, limit: float = _DEFAULT_LIMIT_SECONDS) -> None:
    assert isinstance(timeout, int | float) and not isinstance(timeout, bool), f"timeout is {timeout!r}"
    assert 0 < timeout <= limit, f"timeout {timeout!r} is not within (0, {limit}] seconds"
