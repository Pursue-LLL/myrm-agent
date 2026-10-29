"""Credential redaction of a shell command that is stored or shown.

A command is kept by the audit log and by the background-job registry, and read back by the agent. Its credentials sit
in three shapes: after a command name that takes one (``curl -u``, ``sshpass -p``), after a credential-named parameter
(``--token x``, ``API_KEY=x``), and inside a value shape (``sk-...``, ``user:pw@host``). The shared redactor knows the
first and the third, and the parameters whose name says a credential (``--db-password``). This module adds the ones
whose name only hints at it (``--key``, ``--auth``, ``--bearer``): the shared redactor keeps ``sort --key=2`` readable in
a file or a tool result, while a text known to be a command masks it.

[INPUT]
- bounded_replace::_replace_pattern_bounded (POS: Bounded regex replacement, the ReDoS guard of every redaction pass)
- engine::redact_sensitive_text (POS: Redaction pipeline and public API of the redactor)

[OUTPUT]
- redact_command_line(command) -> str — the command with every credential masked; whitespace and line breaks as written

[POS]
Entry of the commands the audit log and the background-job registry keep; ``agent/meta_tools/bash`` calls it for both.
"""

from __future__ import annotations

import re

from .bounded_replace import _replace_pattern_bounded
from .engine import redact_sensitive_text

# A long option is named by one of these words (``--key``, ``--auth``); an assignment by a name that ends in one (``MY_TOKEN=x``).
_KEYWORDS = (
    "token", "password", "passwd", "pwd", "api_key", "apikey", "api-key", "secret", "key", "auth",
    "credential", "credentials", "access_key", "access-key", "private_key", "private-key", "bearer", "authorization",
)  # fmt: skip
_NAMES = "|".join(re.escape(keyword) for keyword in _KEYWORDS)

# A value is one quoted string or one run of unquoted characters. A single-quoted string ends at the next ``'``, a
# double-quoted one at the next ``"`` that no backslash escapes, and what is inside holds anything (a space, a separator,
# the other kind of quote). A run of unquoted characters ends at whitespace, a quote, a separator, a bracket or a
# backtick, and a backslash keeps the next character in it. A quote that follows a value is never read as its next part:
# a credential typed inside a quoted argument (``-e "API_KEY=x" -e "B=1"``) is followed by the quote that closes that
# argument, and the arguments after the value stay as written. A quoted string that is empty or never closes has nothing
# or no end to mask and is not matched.
_VALUE = r"""(?:'[^']+'|"(?:[^"\\]|\\.)+"|(?:\\.|[^\s"'`;|&<>()\\])+)"""

# ``--token=x`` / ``--token x`` / ``--token="x"`` and the environment form ``TOKEN=x``. A short option (``-t x``) has no
# name to go by: the command rules and the shared redactor handle those, this pass does not guess.
_LONG_OPTION_RE = re.compile(rf"--({_NAMES})[=\s]+{_VALUE}", re.IGNORECASE)
_ASSIGNMENT_RE = re.compile(rf"({_NAMES})={_VALUE}", re.IGNORECASE)


def _redact_named_parameters(command: str) -> str:
    """Mask the value of every credential-named parameter; whitespace and line breaks stay as written."""
    command = _replace_pattern_bounded(command, _LONG_OPTION_RE, lambda m: f"--{m.group(1)}=***REDACTED***")
    return _replace_pattern_bounded(command, _ASSIGNMENT_RE, lambda m: f"{m.group(1)}=***REDACTED***")


def redact_command_line(command: str) -> str:
    """Return ``command`` with every credential in it masked: the named parameters, then the shared redactor."""
    if not command or not isinstance(command, str):
        return command
    return redact_sensitive_text(_redact_named_parameters(command))
