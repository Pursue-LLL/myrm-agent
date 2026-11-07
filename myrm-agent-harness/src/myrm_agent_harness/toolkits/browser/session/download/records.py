"""Records of the download domain: what was saved, what was not kept and why, and where a session's downloads stood.

[INPUT]
- dataclasses (POS: immutable value types)

[OUTPUT]
- DownloadResult: one saved download
- DownloadRefusal: one download that was not kept, with the reason the agent is told
- DownloadMark / DownloadActivity: a moment in a session's downloads, and what was saved or refused after it

[POS]
The shapes the download manager, its storage and the session-level download APIs exchange. A reason is written for the
agent that reads it: it names no address, so it is safe to show.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadResult:
    """Immutable download result."""

    url: str
    path: str
    file_name: str
    file_size: int
    file_type: str | None = None


@dataclass(frozen=True)
class DownloadRefusal:
    """A download the page started that was not kept, and why."""

    file_name: str
    reason: str


@dataclass(frozen=True)
class DownloadMark:
    """How many downloads were saved and refused when it was taken; ``DownloadActivity`` counts from there."""

    saved: int = 0
    refused: int = 0


@dataclass(frozen=True)
class DownloadActivity:
    """The downloads saved and refused after a ``DownloadMark``."""

    saved: tuple[DownloadResult, ...] = ()
    refused: tuple[DownloadRefusal, ...] = ()
