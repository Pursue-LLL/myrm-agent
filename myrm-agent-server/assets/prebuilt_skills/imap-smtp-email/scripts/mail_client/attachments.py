"""Saving of downloaded attachments for the imap-smtp-email skill script: a new file for each, never a replacement.

[INPUT]
- mail_client.transport: fail, the script's JSON error exit

[OUTPUT]
- MAX_SAME_NAME: how many files of one name a directory may hold before a download refuses another
- save_new: write bytes to ``name`` in a directory, or to ``stem-1.ext`` to ``stem-999.ext`` when that name is taken; a
  file, directory or symlink of that name, one that points nowhere included, is taken, and none is written through or
  replaced; ``.`` and ``..`` are taken too, so the file stays inside the directory; a write that fails leaves no file
  behind and raises as it did; a directory that cannot be written raises at once, not after every number is tried

[POS]
Disk half of the email_manager.py facade; no network. An attachment name comes from an untrusted message, and the output
directory may be shared or already hold the user's own files, so a download creates its file exclusively instead of
looking for a free name first and writing afterwards.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from mail_client.transport import fail

MAX_SAME_NAME = 1000  # a message that repeats one name must not make the search for a free number run without end


def save_new(directory: Path, name: str, data: bytes) -> Path:
    """Write *data* to ``name`` in *directory*, or to ``stem-1.ext``, ``stem-2.ext`` ... when taken; replaces nothing."""
    first = directory / name
    for counter in range(MAX_SAME_NAME):
        path = directory / f"{first.stem}-{counter}{first.suffix}" if counter else first
        try:
            handle = path.open("xb")
        except FileExistsError:
            continue
        try:
            with handle:
                handle.write(data)
        except BaseException:
            # The exclusive create makes the file ours, so removing it cannot touch anyone else's; a removal that fails
            # must not hide why the write did.
            with contextlib.suppress(OSError):
                path.unlink()
            raise
        return path
    fail(f"Too many files named {name} in {directory}; remove some of them or pass a different --output-dir")
