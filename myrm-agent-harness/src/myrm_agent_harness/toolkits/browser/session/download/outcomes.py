"""What a session's downloads came to: the files saved, the downloads not kept, and what no answer has told the agent yet.

[INPUT]
- session.download.records::DownloadResult, DownloadRefusal, DownloadMark, DownloadActivity (POS: the shapes the download manager, its storage and the session-level download APIs exchange)

[OUTPUT]
- DownloadOutcomes: the ledger a download manager records into and the session-level reports read from
- REFUSALS_KEPT / UNANNOUNCED_KEPT: how many refusals are remembered, and how many outcomes wait for an answer to carry them

[POS]
The bookkeeping half of the download domain, kept apart from the manager that decides what happens to a download.
Saved files are kept in full; refusals only as the latest few, with a running total so a report can count from a mark.
A download a page starts can settle after the action that started it was answered, so what no answer has carried yet
waits in a short queue: the answer to the action that started it takes its outcomes from there (``report_since``) and a
later answer takes whatever is left (``take_unannounced``), so the agent hears of every outcome once.
"""

from __future__ import annotations

from collections import deque

from .records import DownloadActivity, DownloadMark, DownloadRefusal, DownloadResult

# A page can start refused downloads without end, so only the latest few are remembered.
REFUSALS_KEPT = 5
# Likewise for outcomes waiting to be told; ``list_downloads`` still shows every saved file.
UNANNOUNCED_KEPT = 5


class DownloadOutcomes:
    """Saved files, refusals and the not yet announced outcomes of the downloads a page started."""

    def __init__(self) -> None:
        self._saved: list[DownloadResult] = []
        self._refusals: deque[DownloadRefusal] = deque(maxlen=REFUSALS_KEPT)
        self._refused_total = 0
        self._unannounced: deque[DownloadResult | DownloadRefusal] = deque(maxlen=UNANNOUNCED_KEPT)

    @property
    def saved(self) -> list[DownloadResult]:
        """Every saved file, oldest first."""
        return list(self._saved)

    @property
    def refusals(self) -> tuple[DownloadRefusal, ...]:
        """The latest downloads that were not kept, oldest first."""
        return tuple(self._refusals)

    def mark(self, started: int) -> DownloadMark:
        """Where the outcomes stand now; ``started`` is how many downloads the page has started so far."""
        return DownloadMark(saved=len(self._saved), refused=self._refused_total, started=started)

    def record_saved(self, result: DownloadResult) -> None:
        self._saved.append(result)

    def record_refusal(self, refusal: DownloadRefusal) -> None:
        self._refusals.append(refusal)
        self._refused_total += 1

    def leave_unannounced(self, outcome: DownloadResult | DownloadRefusal) -> None:
        """Hold the outcome of a page-started download until an answer carries it."""
        self._unannounced.append(outcome)

    def report_since(self, mark: DownloadMark) -> DownloadActivity:
        """What was saved or refused after ``mark``; the answer that carries it announces it, so it stops waiting."""
        refused_since = self._refused_total - mark.refused
        activity = DownloadActivity(
            saved=tuple(self._saved[mark.saved :]),
            refused=tuple(self._refusals)[-refused_since:] if refused_since else (),
        )
        announced = {id(outcome) for outcome in (*activity.saved, *activity.refused)}
        self._unannounced = deque(
            (outcome for outcome in self._unannounced if id(outcome) not in announced), maxlen=UNANNOUNCED_KEPT
        )
        return activity

    def take_unannounced(self) -> DownloadActivity:
        """Hand over, once, the outcomes no answer has carried yet."""
        activity = DownloadActivity(
            saved=tuple(outcome for outcome in self._unannounced if isinstance(outcome, DownloadResult)),
            refused=tuple(outcome for outcome in self._unannounced if isinstance(outcome, DownloadRefusal)),
        )
        self._unannounced.clear()
        return activity
