"""Download actions of the browser tools: what the agent is told about a file that was saved or not kept.

[INPUT]
- common::mark_untrusted (POS: unified browser output security boundary; credential redaction + untrusted-content wrapping)
- session.download::DownloadError, DownloadActivity, DownloadMark (POS: the error of a download that is not kept, and the downloads saved or refused after a moment)
- session.browser_session::BrowserSession (POS: browser session aggregate root; download APIs)

[OUTPUT]
- run_download_url / list_downloads_report: the ``download_url`` and ``list_downloads`` actions of browser_manage_tool
- describe_downloads_since: the notes a browser tool appends to an action that may have started downloads (a click, a navigation to a file)
- late_downloads_notice: the notice a later answer carries for downloads that settled after the action that started them was answered

[POS]
Agent-facing text of the download actions. A file name and a refusal reason can come from a hostile page, so every
answer that carries one is wrapped as untrusted content; a download that is not kept is answered with its reason,
never with a bare failure.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..session.download import DownloadError
from .common import mark_untrusted

if TYPE_CHECKING:
    from ..session import BrowserSession
    from ..session.download import DownloadActivity, DownloadMark

# An action that starts a download starts it at once, but the browser does not always report it before the action
# returns, so a report waits this long before it asks which downloads are in flight. Every click pays it, so it is
# kept short: a download that starts later is not in the answer of the action, the next answer carries it.
_DOWNLOAD_START_GRACE_S = 0.05

_LATE_DOWNLOADS = "Downloads from earlier actions have settled since:"


async def run_download_url(session: BrowserSession, value: str) -> str:
    """Download ``value`` and say where the file is, or why it was not kept."""
    url = value.strip()
    if not url:
        return "Error: 'value' must be a URL to download"
    try:
        result = await session.download_url(url)
    except DownloadError as failure:
        return mark_untrusted(f"Download failed: {failure.reason}")
    return mark_untrusted(
        f"Downloaded: {result.file_name} ({result.file_size} bytes)\n"
        f"Path: {result.path}\nType: {result.file_type or 'unknown'}"
    )


def list_downloads_report(session: BrowserSession) -> str:
    """The files this session saved, and the latest downloads a page started that were not kept."""
    session.take_unannounced_downloads()  # the listing tells the agent all that a later answer would add
    downloads = session.list_downloads()
    refusals = session.download_refusals
    if not downloads and not refusals:
        return "No files downloaded yet."
    lines: list[str] = []
    if downloads:
        lines.append(f"Downloaded files ({len(downloads)}):")
        lines.extend(f" - {dl.file_name} ({dl.file_size} bytes): {dl.path}" for dl in downloads)
    if refusals:
        lines.append(f"Downloads not kept ({len(refusals)}):")
        lines.extend(f" - {refusal.file_name}: {refusal.reason}" for refusal in refusals)
    return mark_untrusted("\n".join(lines))


def describe_download_activity(activity: DownloadActivity) -> str:
    """The lines an answer carries for the downloads an action started (empty when it started none)."""
    lines = [
        f"File downloaded: {saved.file_name} ({saved.file_size} bytes)\nPath: {saved.path}" for saved in activity.saved
    ]
    lines.extend(f"Download refused: {refusal.file_name}: {refusal.reason}" for refusal in activity.refused)
    return "\n".join(lines)


async def describe_downloads_since(session: BrowserSession, mark: DownloadMark) -> str:
    """``describe_download_activity`` of the downloads the page started after ``mark``, once they have settled."""
    if not session.download_enabled:
        return ""
    await asyncio.sleep(_DOWNLOAD_START_GRACE_S)
    return describe_download_activity(await session.downloads_since(mark))


def late_downloads_notice(activity: DownloadActivity) -> str:
    """The untrusted-wrapped notice for downloads that settled after their action was answered (empty for none)."""
    notes = describe_download_activity(activity)
    return mark_untrusted(f"{_LATE_DOWNLOADS}\n{notes}") if notes else ""
