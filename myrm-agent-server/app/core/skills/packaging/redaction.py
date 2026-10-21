"""Export-time secret redaction for skill file trees (business layer).

[INPUT]
- myrm_agent_harness.agent.skills.security.content_sanitizer::content_sanitizer, Redaction
  (POS: line-level secret / home-path detection with structured diffs.)

[OUTPUT]
- RedactionOutcome: files to pack plus the findings left after the user's decisions.
- redact_files: pure, CPU-bound scan/redact over a file tree (run it in a worker thread).
- review_digest: fingerprint of the exact file tree a redaction preview was computed from.

[POS]
Single redaction path shared by single-skill export, expert export and Marketplace
export, so no export route can ship skill files without the same ContentSanitizer
pass. Binary files are never decoded or rewritten.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from myrm_agent_harness.agent.skills.security.content_sanitizer import (
    Redaction,
    content_sanitizer,
)

__all__ = ["RedactionOutcome", "redact_files", "review_digest"]


@dataclass(frozen=True)
class RedactionOutcome:
    """Result of one redaction pass over a file tree."""

    files: dict[str, bytes]
    redactions: dict[str, list[Redaction]]

    @property
    def is_safe(self) -> bool:
        """True when no unresolved finding remains."""
        return not self.redactions


def redact_files(
    files: Mapping[str, bytes],
    *,
    apply: bool,
    ignored: Mapping[str, Sequence[int]] | None = None,
) -> RedactionOutcome:
    """Scan ``files`` and, when ``apply`` is set, rewrite flagged text files.

    ``ignored`` maps a file path to the finding indices the user chose to keep
    (indices are positions in the unfiltered scan, as shown by the preview).
    ``redactions`` only lists findings that were not ignored. Scanning is
    CPU-bound (~1 s/MB), so async callers run this in a worker thread.
    """
    packed: dict[str, bytes] = {}
    findings: dict[str, list[Redaction]] = {}
    for path, content in files.items():
        kept = list(ignored[path]) if ignored and path in ignored else None
        result = content_sanitizer.sanitize(content, path, ignored_indices=kept)
        if result.is_safe:
            packed[path] = content
            continue
        findings[path] = result.redactions
        packed[path] = result.sanitized_content.encode("utf-8") if apply else content
    return RedactionOutcome(files=packed, redactions=findings)


def review_digest(files: Mapping[str, bytes]) -> str:
    """Fingerprint a file tree so an export can prove it matches the reviewed preview.

    Finding indices are only meaningful for the exact content that was scanned;
    if a skill changes between preview and export, the same index could point at
    a different secret.
    """
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files[path]).digest())
    return digest.hexdigest()
