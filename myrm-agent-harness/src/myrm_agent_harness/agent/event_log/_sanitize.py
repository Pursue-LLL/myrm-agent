"""Write-side redaction of event payloads.

[INPUT]
- core.security.redact::redact_command_line (POS: Entry of the commands the audit log, the background-job registry and the event log keep: masks every credential in a command string)
- core.security.redact::redact_nested (POS: Shared walker of the redaction domain: bounded in depth, cuts a container that holds itself)
- core.security.detection.leak_detector::redact_leaks (POS: Output-side credential leak detector: credential patterns, Shannon entropy and PEM blocks)

[OUTPUT]
- sanitize_event_data: returns a redacted copy of an event payload; a payload that cannot be redacted is replaced by a marker, never returned as it is

[POS]
Pure filter between ``EventLogger.log`` and the backend. Masks secrets in nested dict/list/tuple payloads (tool
args/results, error diagnostics) like top-level fields and withholds a payload it cannot redact. The shared walker
bounds the depth and cuts a container where it holds itself; this module supplies the text rule, which stays light
because it runs on every event.
"""

from __future__ import annotations

import logging
import re
from typing import cast

from myrm_agent_harness.core.security.detection.leak_detector import redact_leaks
from myrm_agent_harness.core.security.redact import redact_command_line, redact_nested

logger = logging.getLogger(__name__)

# A key whose last word is ``command`` or ``cmd`` (``command``, ``verify_command``, ``rerun_cmd``) holds a command line.
_COMMAND_KEY = re.compile(r"(?:^|_)(?:command|cmd)$")


def sanitize_event_data(data: dict[str, object]) -> dict[str, object]:
    """Return ``data`` with secrets and PII removed from every string it holds.

    A string under a command key is masked as a command line first: the leak
    detector takes the value after ``--key`` for an ordinary word. When the
    payload cannot be redacted the original is withheld and a marker payload is
    returned, so a failure never writes a credential to the log.
    """
    try:
        return cast("dict[str, object]", redact_nested(data, _redact_text))
    except Exception as exc:
        # Only the exception type is logged: its message may quote the payload.
        logger.warning("Event payload withheld, redaction failed: %s", type(exc).__name__)
        return {"_redaction_failed": True}


def _redact_text(key: str, text: str) -> str:
    return redact_leaks(redact_command_line(text) if _COMMAND_KEY.search(key) else text)
