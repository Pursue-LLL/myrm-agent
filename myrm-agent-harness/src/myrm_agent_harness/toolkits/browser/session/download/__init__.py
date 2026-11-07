"""File downloads of a browser session: admitted, judged and saved under bounded, unique names, or discarded.

[INPUT]
- config::DownloadConfig, PageStartedPolicy (POS: where a download manager keeps files, how much, for how long, and which kinds)
- errors::DownloadError (POS: the error of a download that is not kept)
- manager::DownloadManager (POS: listens for, judges, processes and records the downloads of a session)
- records::DownloadResult, DownloadRefusal, DownloadMark, DownloadActivity (POS: the shapes the manager and the session-level download APIs exchange)

[OUTPUT]
- DownloadConfig, PageStartedPolicy: the settings that turn download support on for a ``BrowserSession``
- DownloadManager: the manager a session runs
- DownloadResult, DownloadRefusal, DownloadMark, DownloadActivity: what a session saved, what it did not keep, and the moment a report counts from
- DownloadError: a download that is not kept, with the reason

[POS]
Download domain of the browser session. The session-level APIs over it live in ``browser_session_download_mixin.py``;
the tool layer imports the error and the records from here.
"""

from .config import DownloadConfig, PageStartedPolicy
from .errors import DownloadError
from .manager import DownloadManager
from .records import DownloadActivity, DownloadMark, DownloadRefusal, DownloadResult

__all__ = [
    "DownloadActivity",
    "DownloadConfig",
    "DownloadError",
    "DownloadManager",
    "DownloadMark",
    "DownloadRefusal",
    "DownloadResult",
    "PageStartedPolicy",
]
