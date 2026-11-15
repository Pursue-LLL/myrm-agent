"""The released statements keep their positions in ``MIGRATION_STATEMENTS`` and in ``INDEX_STATEMENTS``.

The engine takes each statement's version from its list index. A statement inserted in the middle moves every later
one onto its predecessor's version, so a database that applied the old list skips the displaced statement and the
engine only logs a checksum mismatch. New statements go at the end.
"""

from __future__ import annotations

import hashlib

from app.database.migrations import INDEX_STATEMENTS, MIGRATION_STATEMENTS

# SHA-256 of the first ``_RELEASED_COUNT`` statements joined by newlines, taken when this guard was added.
_RELEASED_COUNT = 245
_RELEASED_DIGEST = "657661369588186812ccc65686026ed957098bf5252c0bd13a6a0b2d4aa97e9d"

# The same for ``INDEX_STATEMENTS``: its first ``_RELEASED_INDEX_COUNT`` statements.
_RELEASED_INDEX_COUNT = 160
_RELEASED_INDEX_DIGEST = "66e6a74f12823707c7a63cfa9641a5e9328f6b318f88661a0bcca3d2f0f8c5b9"


def test_released_statements_keep_their_positions() -> None:
    released = "\n".join(MIGRATION_STATEMENTS[:_RELEASED_COUNT])

    assert hashlib.sha256(released.encode()).hexdigest() == _RELEASED_DIGEST, (
        f"One of the first {_RELEASED_COUNT} migration statements was edited, removed or displaced; "
        "append new statements at the end of MIGRATION_STATEMENTS instead."
    )


def test_released_index_statements_keep_their_positions() -> None:
    released = "\n".join(INDEX_STATEMENTS[:_RELEASED_INDEX_COUNT])

    assert hashlib.sha256(released.encode()).hexdigest() == _RELEASED_INDEX_DIGEST, (
        f"One of the first {_RELEASED_INDEX_COUNT} index statements was edited, removed or displaced; "
        "append new statements at the end of INDEX_STATEMENTS instead."
    )
