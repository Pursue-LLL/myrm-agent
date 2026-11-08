"""The error of a download that is not kept.

[OUTPUT]
- DownloadError: a download that is not kept, raised with the reason the agent is told

[POS]
Raised by the download storage and manager, caught by the browser tools that report it. Its reason is written for the
agent that reads it and names no address; the detail is for the log only.
"""

from __future__ import annotations


class DownloadError(Exception):
    """A download that is not kept.

    ``reason`` is what the agent is told. ``detail`` is for the log only: the browser's own words, which can be
    technical and can name a path.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail
