"""Checks that turn a pattern match of a built-in risk rule into a hit.

[INPUT]
- myrm_agent_harness.core.security.detection.pii_patterns::china_id_valid, is_placeholder (POS: Single definition of the built-in PII patterns and their validators: classification, redaction and pseudonymization all read it, so they never disagree about what a hit is.)
- myrm_agent_harness.core.security.detection.secret_value::secret_value_span, is_reference_token (POS: The one definition of a secret value versus a reference to one, and of a token made only of readable words and numbers.)

[OUTPUT]
- is_confirmed_match: whether what a built-in rule's pattern matched is a real hit

[POS]
A pattern finds what a value looks like; whether it is one takes the checks the privacy classifier and the leak detector
apply to the same data. Running them here keeps the channel gate agreeing with them about what an ID number, a phone number,
an email address and a secret are, so ``password = input()`` and ``token = os.environ[...]`` in pasted code are not held
while ``password: Zk9#mango42`` is. The gate refuses a message, so it adds what a refusal needs and masking does not: a
value that documentation fills in (``YourSecurePassword123!``, ``change_me``) or a pointer into a secret store
(``env:API_KEY``) is not a secret either, and a session or bearer token is held only when it is long and random
(``session-1`` and ``test-token-123`` are fixtures).
"""

from __future__ import annotations

import regex
from myrm_agent_harness.core.security.detection.pii_patterns import china_id_valid, is_placeholder
from myrm_agent_harness.core.security.detection.secret_value import is_reference_token, secret_value_span

# Sample values ("user@example.com", "00000000000") are not a person's data.
_REJECTS_PLACEHOLDERS = frozenset({"email_address", "cn_mobile_number"})

# Rules whose pattern captures the ``value`` of an assignment (and, for most, its ``key``); a connection string's value is
# its password.
_ASSIGNMENT_RULES = frozenset({"credential_assignment", "env_file_secret", "db_connection_string"})

# A session or bearer token is long and random: a value shorter than this, or made only of readable words and numbers, is a
# fixture or an example. Real session ids (32 hex characters, a framework's signed cookie) and bearer tokens are longer.
_MIN_SESSION_TOKEN_LENGTH = 16

# The ``key`` of the header alternative of the session rule: its ``value`` is the rest of the line, a list of ``name=value``
# cookies, of which only those that hold a session or a credential count (``theme=dark`` and ``_ga=GA1.2.3.4`` are not
# secrets, whatever their length). A cookie ends at ``;`` or at a blank, so a pasted line that lost its separators still
# gives each of them.
_COOKIE_HEADERS = frozenset({"cookie", "set-cookie"})
_COOKIE_PAIR_RE = regex.compile(r"(?P<name>[\w.-]+)=(?P<value>[^;\s]+)")
_CREDENTIAL_COOKIE_NAME_RE = regex.compile(
    r"sess|(?<![a-z])sid(?![a-z])|auth|token|jwt|login|remember|secret|passw", regex.IGNORECASE
)

# Documentation cuts a token short with an ellipsis ("Bearer eyJhbGci...", "sk-ant-oat01-…"); a whole secret has none.
_ELLIPSES = ("...", "\u2026")

# Where the value of an assignment ends although the pattern's ``[^\s"']+`` runs on: at the next query parameter
# (``api_key=abc&profile=x``) and at the first non-ASCII punctuation mark (the full-width bracket or comma after a value in
# Chinese prose: ``secret: isSecret（N3）``). Non-ASCII symbols (``€``, ``£``, ``°``) stay in the value, because passwords
# have them.
_VALUE_END_RE = regex.compile(r"&[A-Za-z_]\w*=|(?![\x00-\x7f])\p{P}")

# A value that starts with one of these words is the one a reader is told to fill in: ``your_api_key``,
# ``CHANGE-TO-A-UNIQUE-64-CHAR-SECRET-KEY``, ``YourSecurePassword123!``; a vendor prefix of letters may stand before it
# (``sk-YOUR_API_KEY``). In any case the word ends at a separator or at the end of the value; written in camel case it ends
# at the next capital. A word that runs on is part of a password: ``Yourdog2012!`` and ``ENTERPRISE2012!`` are secrets.
_PLACEHOLDER_START_RE = regex.compile(
    r"(?:[A-Za-z]{1,6}[-_])?(?i:your|change|replace|example|placeholder|dummy|sample|insert|enter)(?:[-_]|$)"
    r"|(?:[Yy]our|[Cc]hange|[Rr]eplace|[Ee]xample|[Pp]laceholder|[Dd]ummy|[Ss]ample|[Ii]nsert|[Ee]nter)(?=[A-Z])"
)

# A pointer into a secret store names where the secret is kept and does not carry it: ``env:GEMINI_API_KEY``,
# ``vault:secret/data/db#password``.
_SECRET_STORE_POINTER_RE = regex.compile(r"(?i:env|vault):\S")


def is_confirmed_match(rule_id: str, match: regex.Match[str]) -> bool:
    """Whether *match*, which the pattern of the rule *rule_id* found, is a real hit; a rule without a check always is."""
    if rule_id == "cookie_session_like":
        return _holds_session_token(match)
    if rule_id in _ASSIGNMENT_RULES:
        return _assigns_secret(match)
    if rule_id == "cn_id_card":
        return china_id_valid(match.group())
    if rule_id in _REJECTS_PLACEHOLDERS:
        return not is_placeholder(match.group())
    return True


def _assigns_secret(match: regex.Match[str]) -> bool:
    """Whether the ``value`` group is a secret and not a reference to one (call, identifier, template), a mask, a word,
    a placeholder or a token cut short with an ellipsis.

    A pattern the user edited to have no ``value`` group has nothing to check, so its matches count.
    """
    groups = match.groupdict()
    value = groups.get("value")
    if value is None:
        return True
    if _is_cut_short(value):
        return False
    value = _cut_at_value_end(value)
    start = match.start("value")
    span = secret_value_span(match.string, start, start + len(value), allow_letters_only=False, key=groups.get("key") or "")
    return span is not None and not _PLACEHOLDER_START_RE.match(value) and not _SECRET_STORE_POINTER_RE.match(value)


def _holds_session_token(match: regex.Match[str]) -> bool:
    """Whether the match of the session rule holds a session or bearer token: the assigned value is a secret and, being
    long and random, a token (``sessionid=9f8e7d6c5b4a3210fedcba``, ``Authorization: Bearer <opaque value>``), or the
    cookie header lists a cookie of a session or a credential whose value is one.

    A pattern the user edited to have no ``value`` group has nothing to check, so its matches count.
    """
    groups = match.groupdict()
    value = groups.get("value")
    if value is None:
        return True
    if (groups.get("key") or "").lower() in _COOKIE_HEADERS:
        return _cookie_header_holds_session(value)
    return _assigns_secret(match) and _is_session_token(_cut_at_value_end(value))


def _cookie_header_holds_session(header: str) -> bool:
    """Whether a list of ``name=value`` cookies (a ``Cookie`` or ``Set-Cookie`` line) has a credential cookie with a
    token as its value."""
    return any(
        _CREDENTIAL_COOKIE_NAME_RE.search(cookie.group("name"))
        and not _is_cut_short(cookie.group("value"))
        and _is_session_token(cookie.group("value"))
        for cookie in _COOKIE_PAIR_RE.finditer(header)
    )


def _is_session_token(value: str) -> bool:
    return not is_reference_token(value, min_length=_MIN_SESSION_TOKEN_LENGTH)


def _is_cut_short(value: str) -> bool:
    return any(ellipsis in value for ellipsis in _ELLIPSES)


def _cut_at_value_end(value: str) -> str:
    end = _VALUE_END_RE.search(value)
    return value if end is None else value[: end.start()]
