"""Boundary-checked, bounded reads of the rule files of one scan.

The repository decides which rule files exist, where they link to, how many there are and how large they are. A rule file that is a symlink to a
file outside the workspace would put that file into the system message; a very large or very numerous set would hold up every model call, and
the scan of a workspace that is not trusted yet as well. One guard serves one scan: it keeps the files inside the boundary and the reading inside
the budgets.

[INPUT]
- core.security.path::is_within_boundary (POS: boundary check on real paths, immune to symlink escape)

[OUTPUT]
- RuleReadGuard: reads one rule file at a time within the boundary and the budgets of its scan
- RuleRead: the text of a read, or the reason it was refused
- MAX_RULE_FILE_READ_CHARS, MAX_RULE_FILES_PER_SCAN, MAX_RULE_CHARS_PER_SCAN, MAX_REFUSAL_NOTES: the limits

[POS]
Read guard of the workspace rule scan. Decides whether a candidate file may be read, reads it in text mode up to the per-file limit (so its text is
what ``Path.read_text`` returns, line endings included) and charges the scan's file and character budgets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.core.security.path import is_within_boundary

logger = logging.getLogger(__name__)

# Over the 293 open-source repositories whose scan reads rule files, one scan reads at most 159 files, 114,618 characters in one file and 377,804
# characters in all; every limit is at least twice that, so only a layout nobody wrote by hand reaches them.
MAX_RULE_FILE_READ_CHARS = 256_000
MAX_RULE_FILES_PER_SCAN = 512
MAX_RULE_CHARS_PER_SCAN = 2_000_000
# A refused file is shown to the model and the user as a placeholder; the placeholders of a scan are capped so a repository of links cannot fill the
# prompt with them.
MAX_REFUSAL_NOTES = 3


@dataclass(frozen=True, slots=True)
class RuleRead:
    """``text`` is None when the file is not loaded; ``refusal`` is then the reason to show in its place, None when nothing is shown."""

    text: str | None
    refusal: str | None = None


class RuleReadGuard:
    """The boundary and the budgets of one scan. The budgets are checked before each read, so the last read may pass them by one file."""

    __slots__ = ("_boundary", "_chars_left", "_exhaustion_logged", "_files_left", "_refusal_notes_left")

    def __init__(self, boundary: Path) -> None:
        self._boundary = boundary
        self._files_left = MAX_RULE_FILES_PER_SCAN
        self._chars_left = MAX_RULE_CHARS_PER_SCAN
        self._refusal_notes_left = MAX_REFUSAL_NOTES
        self._exhaustion_logged = False

    def read(self, path: Path) -> RuleRead:
        """Read ``path``, or say why not. Raises ``OSError`` like ``Path.read_text`` when the file cannot be read."""
        if self._files_left <= 0 or self._chars_left <= 0:
            self._log_exhaustion(path)
            return RuleRead(None)
        self._files_left -= 1
        if not is_within_boundary(path, self._boundary):
            return self._refuse(path, "the file is outside this workspace")
        with path.open(encoding="utf-8", errors="replace") as handle:
            text = handle.read(MAX_RULE_FILE_READ_CHARS + 1)
        self._chars_left -= len(text)
        if len(text) > MAX_RULE_FILE_READ_CHARS:
            return self._refuse(path, f"the file is larger than {MAX_RULE_FILE_READ_CHARS} characters")
        return RuleRead(text)

    def _refuse(self, path: Path, reason: str) -> RuleRead:
        if self._refusal_notes_left <= 0:
            logger.debug("Workspace rule file not loaded (%s): %r", reason, str(path))
            return RuleRead(None)
        self._refusal_notes_left -= 1
        logger.warning("Workspace rule file not loaded (%s): %r", reason, str(path))
        return RuleRead(None, reason)

    def _log_exhaustion(self, path: Path) -> None:
        if self._exhaustion_logged:
            return
        self._exhaustion_logged = True
        logger.warning(
            "Workspace rule scan stopped at its budget of %d files or %d characters; first file not loaded: %r",
            MAX_RULE_FILES_PER_SCAN,
            MAX_RULE_CHARS_PER_SCAN,
            str(path),
        )
