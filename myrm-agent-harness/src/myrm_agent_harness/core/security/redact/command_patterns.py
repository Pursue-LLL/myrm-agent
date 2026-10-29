"""Command-line credential rules: ``curl -u/-b``, ``sshpass -p`` and ``mysql -p``.

These four options hold a password or a cookie in a short option whose name says nothing, so no name-based rule sees
them. Each rule is anchored on the command name and stays inside one simple command: a ``|``, ``;``, ``&`` or line
break outside a quoted argument (or the escaped line break of a JSON string) ends it, so ``sort -u a:b`` after a pipe is
not a ``curl`` option. A value that is a variable reference, a missing password, a cookie jar file name or an already
masked value stays readable.

[INPUT]
- bounded_replace::_replace_pattern_bounded (POS: Bounded regex replacement, the ReDoS guard of every redaction pass)
- patterns::_is_env_reference (POS: Compiled regex patterns, keyword guard and shared value-masking helpers of the runtime redactor)

[OUTPUT]
- ``_redact_command_credentials(text)`` — the command-line credential pass of the redaction pipeline

[POS]
Command-line rules of the runtime redactor; ``engine.py`` runs ``_redact_command_credentials`` as one name-based pass.
"""

from __future__ import annotations

import re

from .bounded_replace import _replace_pattern_bounded
from .patterns import _is_env_reference

# One argument: single-quoted, double-quoted, double-quoted inside a JSON string (``\"…\"``) or a bare word.
_QUOTED_ARGUMENT = r"""'[^'\r\n]*'|"[^"\r\n]*"|\\"(?:(?!\\")[^\r\n])*\\\""""
_ARGUMENT = rf"""(?P<value>{_QUOTED_ARGUMENT}|[^\s'"`]+)"""
# The password of ``mysql -p`` follows the option without a space and never starts with ``-``.
_ATTACHED_ARGUMENT = rf"""(?P<value>{_QUOTED_ARGUMENT}|[^\s'"`\-][^\s'"`]*)"""

# The command name is a whole word, not the tail of another name (``mycurl``, ``libcurl``), and may carry a path.
_NOT_GLUED = r"(?<![\w.\-])"


def _command_gap(name: str) -> str:
    """What may lie between the command ``name`` and its option.

    Any character that is not a command separator, and a quoted argument whole (it may hold ``;``, ``|`` or ``&``). The
    escaped line break of a JSON string separates two commands like a real one. The next occurrence of the name ends the
    gap: it starts the same search itself, so a text that repeats the name costs a few steps per occurrence, not the
    full bound of 256.
    """
    return rf"""(?:(?!\\[nr])(?!{_NOT_GLUED}{name}\b)[^|;&\r\n'"]|'[^'\r\n]*'|"[^"\r\n]*"){{0,256}}?"""


_CURL_OPTION_RE = re.compile(
    rf"(?P<head>{_NOT_GLUED}curl\b{_command_gap('curl')}\s(?P<option>-[ub]\s*|--(?:user|cookie)(?:\s+|=))){_ARGUMENT}"
)
_SSHPASS_RE = re.compile(rf"(?P<head>{_NOT_GLUED}sshpass\b{_command_gap('sshpass')}\s-p\s*){_ARGUMENT}")
_MYSQL_RE = re.compile(
    rf"(?P<head>{_NOT_GLUED}mysql(?:dump|admin)?\b{_command_gap('mysql(?:dump|admin)?')}\s-p){_ATTACHED_ARGUMENT}"
)

_MASKED = "***"


def _unquote(value: str) -> tuple[str, str, str]:
    """Split an argument into its opening quote, its content and its closing quote."""
    for quote in ('\\"', '"', "'"):
        if len(value) >= 2 * len(quote) and value.startswith(quote) and value.endswith(quote):
            return quote, value[len(quote) : -len(quote)], quote
    return "", value, ""


def _holds_secret(value: str) -> bool:
    """Whether ``value`` can be a password: it has a letter or digit and is no variable reference or substitution.

    A bare punctuation mark after the option (``sshpass -p, mysql -p)`` in a sentence) and a value that is already
    masked have no letter or digit, so neither is rewritten.
    """
    return any(char.isalnum() for char in value) and not (_is_env_reference(value) or value.startswith("$("))


def _redact_curl_option(m: re.Match[str]) -> str:
    """``-u user:password`` keeps the user name; ``-b name=value; …`` is masked whole unless it names a cookie jar file."""
    opening, content, closing = _unquote(m["value"])
    if m["option"].lstrip("-").strip(" \t=") in ("u", "user"):
        user, colon, password = content.partition(":")
        if not colon or not _holds_secret(password):
            return m[0]
        return f"{m['head']}{opening}{user}:{_MASKED}{closing}"
    if "=" not in content or not _holds_secret(content):
        return m[0]
    return f"{m['head']}{opening}{_MASKED}{closing}"


def _redact_password_argument(m: re.Match[str]) -> str:
    """Replacement for ``sshpass -p`` and ``mysql -p``: the whole argument is the password."""
    opening, content, closing = _unquote(m["value"])
    if not _holds_secret(content):
        return m[0]
    return f"{m['head']}{opening}{_MASKED}{closing}"


def _redact_command_credentials(text: str) -> str:
    """Mask the password or cookie in a ``curl``, ``sshpass`` or ``mysql`` command line.

    A text that never names the command skips its rule, which is nearly every text.
    """
    if "curl" in text:
        text = _replace_pattern_bounded(text, _CURL_OPTION_RE, _redact_curl_option)
    if "sshpass" in text:
        text = _replace_pattern_bounded(text, _SSHPASS_RE, _redact_password_argument)
    if "mysql" in text:
        text = _replace_pattern_bounded(text, _MYSQL_RE, _redact_password_argument)
    return text
