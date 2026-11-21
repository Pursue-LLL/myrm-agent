"""Put the process clock at UTC+8, so a test can tell a time read as UTC from one read as the host's local time.

[INPUT]
- pytest::MonkeyPatch (POS: scoped environment patching that undoes only what its own context set)

[OUTPUT]
- pin_host_clock_to_utc_plus_8: context manager that holds the process clock eight hours ahead of UTC whatever the host
  is set to, raises when the pin did not take (a test must never run unpinned and still pass), and puts the host's own
  zone back on exit; a platform without ``time.tzset`` is left as it is

[POS]
Harness pytest-only helper for tests of code that must read a time without an offset as UTC. On a host already set to
UTC, reading it as local time gives the same answer, so only a clock that is not at UTC tells the two readings apart.
The server's tests keep a twin (``myrm-agent-server/tests/support/host_clock.py``): change one, change both.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

_PINNED_OFFSET_SECONDS = 8 * 3600


@contextmanager
def pin_host_clock_to_utc_plus_8() -> Iterator[None]:
    """Run the block with the process clock eight hours ahead of UTC, then put the host's own zone back."""
    if not hasattr(time, "tzset"):
        yield
        return
    try:
        with pytest.MonkeyPatch.context() as patch:
            # The POSIX spelling needs no zone database: a zone name the host cannot resolve falls back to UTC without a word,
            # and the block would then run on a clock that cannot tell the two readings apart.
            patch.setenv("TZ", "UTC-8")
            time.tzset()
            offset = time.localtime(0).tm_gmtoff
            if offset != _PINNED_OFFSET_SECONDS:
                raise RuntimeError(
                    f"The process clock is {offset} seconds from UTC after the pin, not eight hours ahead"
                )
            yield
    finally:
        time.tzset()
