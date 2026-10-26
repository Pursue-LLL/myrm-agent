"""Tencent ima knowledge-base and notes connector (read-only import into the wiki vault).

[INPUT]
- .job_runner / .operations / .report (POS: cron slice, user operations, status and item report)
- .errors (POS: typed ima failures)

[OUTPUT]
- run_ima_sync_job / ImaJobOutcome: the ``__wiki_ima_sync__`` cron entry
- connect / disconnect / list_libraries / save_selection: account and scope
- start_sync / pause_sync / resume_sync / retry_failed / compile_imported: sync control
- build_status / list_items: read side
- ImaOperationError and the ``Ima*Error`` family

[POS]
Facade of the ima subpackage; see ``_ARCH.md`` for the module map.
"""

from .errors import (
    ImaAuthError,
    ImaError,
    ImaPageUnavailableError,
    ImaPermanentError,
    ImaRateLimitError,
    ImaTooLargeError,
    ImaTransientError,
)
from .job_runner import ImaJobOutcome, run_ima_sync_job
from .operations import (
    ImaOperationError,
    compile_imported,
    connect,
    disconnect,
    list_libraries,
    pause_sync,
    resume_sync,
    retry_failed,
    save_selection,
    start_sync,
)
from .report import build_status, list_items

__all__ = [
    "ImaAuthError",
    "ImaError",
    "ImaJobOutcome",
    "ImaOperationError",
    "ImaPageUnavailableError",
    "ImaPermanentError",
    "ImaRateLimitError",
    "ImaTooLargeError",
    "ImaTransientError",
    "build_status",
    "compile_imported",
    "connect",
    "disconnect",
    "list_items",
    "list_libraries",
    "pause_sync",
    "resume_sync",
    "retry_failed",
    "run_ima_sync_job",
    "save_selection",
    "start_sync",
]
