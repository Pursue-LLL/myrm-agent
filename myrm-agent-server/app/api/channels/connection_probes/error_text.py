"""Error text that is safe to show on the channel settings page.

[INPUT]
- myrm_agent_harness.api::redact_sensitive_text (POS: masks credentials and tokens in free text)

[OUTPUT]
- safe_err_msg: the text of an exception with credentials masked

[POS]
A probe echoes the failure of the service it called, and that text can contain the credentials the user just typed
(a token in a URL, a password in a connection string); every probe answers with it instead of ``str(exc)``.
"""

from __future__ import annotations

from myrm_agent_harness.api import redact_sensitive_text


def safe_err_msg(e: Exception) -> str:
    return redact_sensitive_text(str(e))
