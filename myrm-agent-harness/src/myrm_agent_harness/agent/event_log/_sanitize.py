"""Write-side redaction of event payloads.

[INPUT]
- core.security.redact::redact_command_line (POS: Entry of the commands the audit log, the background-job registry and the event log keep: masks every credential in a command string)
- core.security.detection.leak_detector::redact_leaks (POS: Output-side credential leak detector: credential patterns, Shannon entropy and PEM blocks)

[OUTPUT]
- sanitize_event_data: returns a redacted copy of an event payload; a payload that cannot be redacted is replaced by a marker, never returned as it is

[POS]
Pure filter between ``EventLogger.log`` and the backend. Masks secrets in nested dict/list/tuple payloads (tool
args/results, error diagnostics) like top-level fields and withholds a payload it cannot redact. The walk is bounded in
depth, which keeps it independent of the interpreter stack, and it cuts a container where it holds itself, so a loop
costs one visit per container.
"""

from __future__ import annotations

import logging
import re
from typing import cast

from myrm_agent_harness.core.security.detection.leak_detector import redact_leaks
from myrm_agent_harness.core.security.redact import redact_command_line

logger = logging.getLogger(__name__)

# A key whose last word is ``command`` or ``cmd`` (``command``, ``verify_command``, ``rerun_cmd``) holds a command line.
_COMMAND_KEY = re.compile(r"(?:^|_)(?:command|cmd)$")
# Persisted event payloads nest a handful of levels; a deeper container is replaced, not walked.
_MAX_DEPTH = 32
_TOO_DEEP = "[nesting too deep]"
_CIRCULAR = "[circular reference]"


def sanitize_event_data(data: dict[str, object]) -> dict[str, object]:
    """Return ``data`` with secrets and PII removed from every string it holds.

    A string under a command key is masked as a command line first: the leak
    detector takes the value after ``--key`` for an ordinary word. When the
    payload cannot be redacted the original is withheld and a marker payload is
    returned, so a failure never writes a credential to the log.
    """
    try:
        return cast("dict[str, object]", _redact(data, "", 1, set()))
    except Exception as exc:
        # Only the exception type is logged: its message may quote the payload.
        logger.warning("Event payload withheld, redaction failed: %s", type(exc).__name__)
        return {"_redaction_failed": True}


def _redact(value: object, key: object, depth: int, ancestors: set[int]) -> object:
    """Redact ``value``; ``ancestors`` holds the containers on the path from the payload root to it."""
    if isinstance(value, str):
        is_command = isinstance(key, str) and _COMMAND_KEY.search(key)
        return redact_leaks(redact_command_line(value) if is_command else value)
    if not isinstance(value, dict | list | tuple):
        return value
    if depth > _MAX_DEPTH:
        return _TOO_DEEP
    if id(value) in ancestors:
        return _CIRCULAR
    ancestors.add(id(value))
    if isinstance(value, dict):
        redacted: object = {name: _redact(item, name, depth + 1, ancestors) for name, item in value.items()}
    else:
        items = [_redact(item, key, depth + 1, ancestors) for item in value]
        redacted = items if isinstance(value, list) else tuple(items)
    ancestors.discard(id(value))
    return redacted
