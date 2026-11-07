"""Download actions of the browser tools: what the agent is told about a file that was saved or not kept.

[INPUT]
- common::mark_untrusted (POS: unified browser output security boundary; credential redaction + untrusted-content wrapping)
- session.download::DownloadError, DownloadActivity (POS: the error of a download that is not kept, and the downloads saved or refused after a moment)
- session.browser_session::BrowserSession (POS: browser session aggregate root; download APIs)

[OUTPUT]
- run_download_url / list_downloads_report: the ``download_url`` and ``list_downloads`` actions of browser_manage_tool
- describe_download_activity: the notes browser_interact_tool appends to a click that started downloads

[POS]
Agent-facing text of the download actions. A file name and a refusal reason can come from a hostile page, so every
answer that carries one is wrapped as untrusted content; a download that is not kept is answered with its reason,
never with a bare failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..session.download import DownloadError
from .common import mark_untrusted

if TYPE_CHECKING:
    from ..session import BrowserSession
    from ..session.download import DownloadActivity


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
    """The lines a click is answered with for the downloads it started (empty when it started none)."""
    lines = [
        f"File downloaded: {saved.file_name} ({saved.file_size} bytes)\nPath: {saved.path}" for saved in activity.saved
    ]
    lines.extend(f"Download refused: {refusal.file_name}: {refusal.reason}" for refusal in activity.refused)
    return "\n".join(lines)
