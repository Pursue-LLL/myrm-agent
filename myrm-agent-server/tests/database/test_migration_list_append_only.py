"""The released migration statements keep their positions in ``MIGRATION_STATEMENTS``.

The engine takes each statement's version from its list index. A statement inserted in the middle moves every later
one onto its predecessor's version, so a database that applied the old list skips the displaced statement and the
engine only logs a checksum mismatch. New statements go at the end.
"""

from __future__ import annotations

import hashlib

from app.database.migrations import MIGRATION_STATEMENTS

# SHA-256 of the first ``_RELEASED_COUNT`` statements joined by newlines, taken when this guard was added.
_RELEASED_COUNT = 245
_RELEASED_DIGEST = "657661369588186812ccc65686026ed957098bf5252c0bd13a6a0b2d4aa97e9d"


def test_released_statements_keep_their_positions() -> None:
    released = "\n".join(MIGRATION_STATEMENTS[:_RELEASED_COUNT])

    assert hashlib.sha256(released.encode()).hexdigest() == _RELEASED_DIGEST, (
        f"One of the first {_RELEASED_COUNT} migration statements was edited, removed or displaced; "
        "append new statements at the end of MIGRATION_STATEMENTS instead."
    )
