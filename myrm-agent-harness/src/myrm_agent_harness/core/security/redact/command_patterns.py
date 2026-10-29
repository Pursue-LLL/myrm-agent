"""Command-line credential rules: ``curl``, ``sshpass``, ``mysql``, ``docker login``, ``redis-cli`` and ``openssl``.

Each of these commands takes a password, a cookie or a passphrase in an option whose name says nothing (``-u``, ``-p``,
``-a``), so no name-based rule sees it. Every rule is anchored on the command name and stays inside one simple command:
a ``|``, ``;``, ``&`` or line break outside a quoted argument (or the escaped line break of a JSON string) ends it, so
``sort -u a:b`` after a pipe is not a ``curl`` option; a backslash before the line break continues the command. A value
that is a variable reference, a missing password, a cookie jar file name or an already masked value stays readable.
One ``curl`` command carries a login, a proxy login and a cookie together, and every one of them is masked.

[INPUT]
- bounded_replace::_replace_pattern_bounded (POS: Bounded regex replacement, the ReDoS guard of every redaction pass)
- patterns::_is_env_reference (POS: Compiled regex patterns, keyword guard and shared value-masking helpers of the runtime redactor)

[OUTPUT]
- ``_redact_command_credentials(text)`` — the command-line credential pass of the redaction pipeline

[POS]
Command-line rules of the runtime redactor; ``engine.py`` runs ``_redact_command_credentials`` as the first step of the pipeline, ahead of the generic passes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import NamedTuple

from .bounded_replace import _replace_pattern_bounded
from .patterns import _is_env_reference

# One argument: single-quoted, double-quoted, double-quoted inside a JSON string (``\"…\"``) or a bare word.
_QUOTED_ARGUMENT = r"""'[^'\r\n]*'|"[^"\r\n]*"|\\"(?:(?!\\")[^\r\n])*\\\""""
_ANY_ARGUMENT = rf"""{_QUOTED_ARGUMENT}|[^\s'"`]+"""
_ARGUMENT = rf"(?P<value>{_ANY_ARGUMENT})"
# An argument that is skipped over, not masked.
_SKIPPED_ARGUMENT = rf"(?:{_ANY_ARGUMENT})"
# The password of ``mysql -p`` follows the option without a space and never starts with ``-``.
_ATTACHED_ARGUMENT = rf"""(?P<value>{_QUOTED_ARGUMENT}|[^\s'"`\-][^\s'"`]*)"""

# The command name is a whole word, not the tail of another name (``mycurl``, ``libcurl``), and may carry a path.
_NOT_GLUED = r"(?<![\w.\-])"

# A backslash before a line break, raw or inside a JSON string, joins the next line to the command.
_CONTINUATION = r"\\\r?\n|\\\\\\(?:r\\n|n)"
# The option follows blank space, or the line break that a continuation has just consumed.
_BLANK_BEFORE_OPTION = r"(?:\s|(?<=\n)|(?<=\\n))"
_BLANKS = rf"(?:\s|{_CONTINUATION})+"


def _command_units(name: str) -> str:
    """One step inside the command ``name``: a line continuation, any character that is not a command separator, or a
    quoted argument whole (it may hold ``;``, ``|`` or ``&``).

    The escaped line break of a JSON string separates two commands like a real one. The next occurrence of the name
    ends the command: it starts the same search itself, so a text that repeats the name costs a few steps per
    occurrence, not the full bound of 256.
    """
    return rf"""(?:{_CONTINUATION}|(?!\\[nr])(?!{_NOT_GLUED}{name}\b)[^|;&\r\n'"]|'[^'\r\n]*'|"[^"\r\n]*")"""


def _command_gap(name: str) -> str:
    """What may lie between the command ``name`` and its option."""
    return rf"{_command_units(name)}{{0,256}}?"


def _after(name: str, option: str) -> str:
    """The command ``name``, the options and arguments up to ``option`` (the head), and the value that follows."""
    return rf"(?P<head>{_NOT_GLUED}{name}\b{_command_gap(name)}{_BLANK_BEFORE_OPTION}{option}){_ARGUMENT}"


# ``-u`` and ``-U`` may close a cluster of short flags (``-sSu``); curl takes no more than a dozen of them in practice.
_CURL_OPTION = (
    r"(?:(?P<user>-[A-Za-z]{0,12}[uU]\s*|--user(?:\s+|=)|--proxy-user(?:\s+|=))|(?P<cookie>-b\s*|--cookie(?:\s+|=)))"
)
# One curl takes a login, a proxy login and a cookie together: the options after the first one lie in the same command.
_CURL_OPTION_RE = re.compile(_after("curl", _CURL_OPTION) + rf"(?P<tail>{_command_units('curl')}{{0,256}})")
_CURL_FOLLOWING_OPTION_RE = re.compile(rf"(?P<head>{_BLANK_BEFORE_OPTION}{_CURL_OPTION}){_ARGUMENT}")
# sshpass reads its own options up to the command it wraps: ``-f``, ``-d`` and ``-P`` take an argument, ``-e`` and ``-v``
# do not. The first word that is no option starts the wrapped command, whose ``-p`` (``ssh -p 2222``) is a port.
_SSHPASS_RE = re.compile(
    rf"(?P<head>{_NOT_GLUED}sshpass\b(?:{_BLANKS}(?:-[fdP]\s*{_SKIPPED_ARGUMENT}|-[^\sp]\S*))*?{_BLANKS}-p\s*){_ARGUMENT}"
)
_MYSQL_RE = re.compile(
    rf"(?P<head>{_NOT_GLUED}mysql(?:dump|admin)?\b{_command_gap('mysql(?:dump|admin)?')}{_BLANK_BEFORE_OPTION}-p)"
    rf"{_ATTACHED_ARGUMENT}"
)
# ``-p`` is the password of ``docker login`` and a port of ``docker run``; ``--password-stdin`` carries none.
_DOCKER_LOGIN_RE = re.compile(
    rf"(?P<head>{_NOT_GLUED}docker{_BLANKS}login\b{_command_gap('docker')}{_BLANK_BEFORE_OPTION}"
    rf"(?:-p\s*|--password(?:\s+|=))){_ARGUMENT}"
)
# ``-a`` and ``--pass`` are the password of ``redis-cli``; its port is ``-p``.
_REDIS_CLI_RE = re.compile(_after("redis-cli", r"(?:-a\s*|--pass(?:\s+|=))"))
# The passphrase source of ``openssl``: ``pass:text`` is the passphrase itself, ``env:``, ``file:`` and ``stdin`` are not.
_OPENSSL_RE = re.compile(_after("openssl", r"-(?:pass|passin|passout|password)\s+"))

_MASKED = "***"
_OPENSSL_LITERAL = "pass:"


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


def _mask_curl_option(m: re.Match[str]) -> str:
    """``-u user:password`` keeps the user name; ``-b name=value; …`` is masked whole unless it names a cookie jar file."""
    opening, content, closing = _unquote(m["value"])
    if m["user"] is not None:
        user, colon, password = content.partition(":")
        masked = f"{user}:{_MASKED}" if colon and _holds_secret(password) else None
    else:
        masked = _MASKED if "=" in content and _holds_secret(content) else None
    return f"{m['head']}{m['value']}" if masked is None else f"{m['head']}{opening}{masked}{closing}"


def _redact_curl_option(m: re.Match[str]) -> str:
    """The first credential option of a curl command and every one after it."""
    return _mask_curl_option(m) + _CURL_FOLLOWING_OPTION_RE.sub(_mask_curl_option, m["tail"])


def _redact_password_argument(m: re.Match[str]) -> str:
    """Replacement for the options whose whole argument is the password (``sshpass``, ``mysql``, ``docker login``, ``redis-cli``)."""
    opening, content, closing = _unquote(m["value"])
    if not _holds_secret(content):
        return m[0]
    return f"{m['head']}{opening}{_MASKED}{closing}"


def _redact_openssl_passphrase(m: re.Match[str]) -> str:
    """``-pass pass:text`` masks the text; a passphrase read from ``env:``, ``file:`` or ``stdin`` is no secret."""
    opening, content, closing = _unquote(m["value"])
    if not content.startswith(_OPENSSL_LITERAL) or not _holds_secret(content[len(_OPENSSL_LITERAL) :]):
        return m[0]
    return f"{m['head']}{opening}{_OPENSSL_LITERAL}{_MASKED}{closing}"


class _Rule(NamedTuple):
    """One command's rule; a text that lacks its ``trigger`` word is not searched, which is nearly every text."""

    trigger: str
    pattern: re.Pattern[str]
    replace: Callable[[re.Match[str]], str]


_RULES: tuple[_Rule, ...] = (
    _Rule("curl", _CURL_OPTION_RE, _redact_curl_option),
    _Rule("sshpass", _SSHPASS_RE, _redact_password_argument),
    _Rule("mysql", _MYSQL_RE, _redact_password_argument),
    _Rule("docker", _DOCKER_LOGIN_RE, _redact_password_argument),
    _Rule("redis-cli", _REDIS_CLI_RE, _redact_password_argument),
    _Rule("openssl", _OPENSSL_RE, _redact_openssl_passphrase),
)


def _redact_command_credentials(text: str) -> str:
    """Mask the password, cookie or passphrase in the command lines the rules know."""
    for rule in _RULES:
        if rule.trigger in text:
            text = _replace_pattern_bounded(text, rule.pattern, rule.replace)
    return text
