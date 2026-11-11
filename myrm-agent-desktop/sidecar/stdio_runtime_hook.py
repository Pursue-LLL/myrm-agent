"""PyInstaller runtime hook: give the sidecar the standard streams its code expects, whoever started it.

Two Windows launches break a backend that prints text:

- From the Tauri shell the sidecar has no console and no console handles to inherit, so Python starts with
  ``sys.stdin``, ``sys.stdout`` and ``sys.stderr`` set to ``None``; uvicorn then fails while configuring its
  logging (``sys.stdout.isatty()``), before the first request is served.
- With stdout redirected to a file or pipe Python encodes it in the ANSI code page (cp1252 on most machines), and
  the first emoji in a startup message raises ``UnicodeEncodeError``.

A null stream replaces a missing one, and the output streams switch to UTF-8 with replacement characters, so no
message can stop the backend.

[INPUT]
- os, sys (POS: the null device and the process's standard streams)

[OUTPUT]
- Import side effect: stdin, stdout and stderr always exist, and the output streams encode UTF-8 with replacement
  characters

[POS]
Runtime hook that build.py injects with ``--runtime-hook``; it runs before the sidecar entry imports the server, so
uvicorn's logging and every startup message find usable standard streams.
"""

import os
import sys

for _name, _mode in (("stdin", "r"), ("stdout", "w"), ("stderr", "w")):
    _stream = getattr(sys, _name)
    if _stream is None:
        # Never closed: the replacement serves the whole process.
        setattr(sys, _name, open(os.devnull, _mode, encoding="utf-8"))
    elif _mode == "w":
        _stream.reconfigure(encoding="utf-8", errors="replace")
