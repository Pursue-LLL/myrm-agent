"""Saving of downloaded attachments for the imap-smtp-email skill script: a new file for each, never a replacement.

[INPUT]
- none: standard library only, so the script still ships on its own

[OUTPUT]
- MAX_SAME_NAME: how many files of one name a directory may hold before a download refuses another
- save_new: write bytes to a file in a directory that is named after ``filename``, any text a sender may have written: a
  character other than a letter, digit, ``.``, ``_`` or ``-`` becomes ``_``, a name of dots only or an empty one becomes
  ``attachment``, and a name too long for a file system is cut at a character boundary with a short extension kept, so
  the file is always one name inside the directory; when that name is taken the file is ``stem-1.ext`` to ``stem-999.ext``,
  and a file, directory or symlink of that name, one that points nowhere included, is taken, and none is written through
  or replaced; a write that fails leaves no file behind and raises as it did; a directory that cannot be written raises at
  once, not after every number is tried; a name taken ``MAX_SAME_NAME`` times raises FileExistsError

[POS]
Disk half of the email_manager.py facade; no network. An attachment name comes from an untrusted message, and the output
directory may be shared or already hold the user's own files, so the name is made safe here, next to the one place that
writes, and the file is created exclusively instead of looking for a free name first and writing afterwards.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

MAX_SAME_NAME = 1000  # a message that repeats one name must not make the search for a free number run without end

_FILE_NAME_BYTES = 255  # what a file name may hold on Linux, counted in bytes
# The number of a copy, ``-999`` at most, is appended to a name, so a name keeps that much of the limit free.
_NAME_BYTES = _FILE_NAME_BYTES - len(f"-{MAX_SAME_NAME - 1}")
_EXTENSION_BYTES = 16  # a longer tail after the last dot is part of the name, not an extension worth keeping


def _file_name(filename: str) -> str:
    """*filename* as one name that is safe to create in a directory and short enough to take a copy's number."""
    name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    if not name.strip("."):
        return "attachment"
    if len(name.encode()) <= _NAME_BYTES:
        return name
    extension = Path(name).suffix
    if len(extension.encode()) > _EXTENSION_BYTES:
        extension = ""
    stem = name[: len(name) - len(extension)]
    room = _NAME_BYTES - len(extension.encode())
    # Cutting the encoded stem can split a character; dropping the broken tail keeps every character whole.
    return stem.encode()[:room].decode(errors="ignore") + extension


def save_new(directory: Path, filename: str, data: bytes) -> Path:
    """Write *data* to a file named after *filename* in *directory*, or ``stem-1.ext``, ``stem-2.ext`` ... when taken."""
    first = Path(_file_name(filename))
    for counter in range(MAX_SAME_NAME):
        path = directory / (f"{first.stem}-{counter}{first.suffix}" if counter else first)
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
    raise FileExistsError(f"Too many files named {first} in {directory}; remove some of them or pass a different --output-dir")
