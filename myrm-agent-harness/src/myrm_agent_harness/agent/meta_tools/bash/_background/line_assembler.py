"""Turns a job's raw byte stream into complete lines and keeps the unfinished last line visible.

[INPUT]
- none (imports no other project module; takes the bytes a pipe or PTY delivers, in chunks of any size)

[OUTPUT]
- LineAssembler: complete lines (decoded, trailing whitespace stripped, over-long lines cut with a count) plus the unfinished tail
- TAIL_CHARS: how many characters of the unfinished line stay visible

[POS]
Reader helper for ``consume_background_entry``: a prompt such as ``Continue? [y/N] `` ends without a newline, so a line
reader never returns it, while a chunk reader sees it the moment the program prints it. The lines it returns are the
ones a line reader would return, so everything downstream of the reader keeps working on whole lines.
"""

from __future__ import annotations

import codecs

# Enough to hold any real prompt and the last fragment of a carriage-return progress line.
TAIL_CHARS = 512


class LineAssembler:
    """Incremental line splitter; memory per line is bounded by ``max_line_chars`` plus the tail window."""

    def __init__(self, *, max_line_chars: int) -> None:
        # Incremental decoding keeps a UTF-8 sequence that a chunk boundary cut in two intact.
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._max = max_line_chars
        self._head: list[str] = []  # kept prefix of the unfinished line, at most ``max_line_chars`` characters
        self._kept = 0
        self._total = 0  # characters of the unfinished line seen so far
        self._trailing_ws = 0  # whitespace characters at the end of the unfinished line
        self._tail = ""  # last ``TAIL_CHARS`` characters of the unfinished line

    @property
    def tail(self) -> str:
        """The unfinished last line (its final ``TAIL_CHARS`` characters); empty right after a newline."""
        return self._tail

    def feed(self, data: bytes) -> list[str]:
        """Consume a chunk; return the lines it completed."""
        text = self._decoder.decode(data)
        lines: list[str] = []
        start = 0
        while (newline := text.find("\n", start)) >= 0:
            lines.append(self._complete(text[start:newline]))
            start = newline + 1
        if start < len(text):
            self._extend(text[start:])
        return lines

    def finish(self) -> list[str]:
        """End of stream: the unfinished line, if any, becomes a line, as a line reader returns it at EOF."""
        rest = self._decoder.decode(b"", final=True)
        if rest:
            self._extend(rest)
        return [self._take()] if self._total else []

    def _complete(self, piece: str) -> str:
        if not self._total:
            # The whole line arrived in this chunk: no state to carry.
            raw = piece.rstrip()
            return self._cut(raw, len(raw))
        self._extend(piece)
        return self._take()

    def _extend(self, piece: str) -> None:
        self._total += len(piece)
        content = piece.rstrip()
        self._trailing_ws = len(piece) - len(content) if content else self._trailing_ws + len(piece)
        room = self._max - self._kept
        if room > 0:
            kept = piece[:room]
            self._head.append(kept)
            self._kept += len(kept)
        self._tail = (self._tail + piece)[-TAIL_CHARS:]

    def _take(self) -> str:
        head = "".join(self._head)
        stripped_total = self._total - self._trailing_ws
        self._head, self._kept, self._total, self._trailing_ws, self._tail = [], 0, 0, 0, ""
        return self._cut(head, stripped_total)

    def _cut(self, text: str, length: int) -> str:
        """``text`` holds the first ``max_line_chars`` characters of a line ``length`` characters long."""
        if length > self._max:
            return f"{text[: self._max]}... [+{length - self._max} chars truncated]"
        return text[:length]
