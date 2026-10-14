"""Checks that turn a pattern match of a built-in risk rule into a hit.

[INPUT]
- myrm_agent_harness.core.security.detection.pii_patterns::china_id_valid, is_placeholder (POS: Single definition of the built-in PII patterns and their validators: classification, redaction and pseudonymization all read it, so they never disagree about what a hit is.)
- myrm_agent_harness.core.security.detection.secret_value::secret_value_span (POS: The one definition of a secret value versus a reference to one.)

[OUTPUT]
- is_confirmed_match: whether what a built-in rule's pattern matched is a real hit

[POS]
A pattern finds what a value looks like; whether it is one takes the checks the privacy classifier and the leak detector
apply to the same data. Running them here keeps the channel gate agreeing with them about what an ID number, a phone number,
an email address and a secret are, so ``password = input()`` and ``token = os.environ[...]`` in pasted code are not held
while ``password: Zk9#mango42`` is. The gate refuses a message, so it adds what a refusal needs and masking does not: a
value that documentation fills in (``YourSecurePassword123!``, ``change_me``) is not a secret either.
"""

from __future__ import annotations

import regex
from myrm_agent_harness.core.security.detection.pii_patterns import china_id_valid, is_placeholder
from myrm_agent_harness.core.security.detection.secret_value import secret_value_span

# Sample values ("user@example.com", "00000000000") are not a person's data.
_REJECTS_PLACEHOLDERS = frozenset({"email_address", "cn_mobile_number"})

# Rules whose pattern captures the ``value`` of an assignment (and, for most, its ``key``); a connection string's value is
# its password.
_ASSIGNMENT_RULES = frozenset({"credential_assignment", "cookie_session_like", "env_file_secret", "db_connection_string"})

# Documentation cuts a token short with an ellipsis ("Bearer eyJhbGci...", "sk-ant-oat01-…"); a whole secret has none.
_ELLIPSES = ("...", "\u2026")

# Where the value of an assignment ends although the pattern's ``[^\s"']+`` runs on: at the next query parameter
# (``api_key=abc&profile=x``) and at the first non-ASCII punctuation mark (the full-width bracket or comma after a value in
# Chinese prose: ``secret: isSecret（N3）``). Non-ASCII symbols (``€``, ``£``, ``°``) stay in the value, because passwords
# have them.
_VALUE_END_RE = regex.compile(r"&[A-Za-z_]\w*=|(?![\x00-\x7f])\p{P}")

# A value that starts with one of these words is the one a reader is told to fill in: ``your_api_key``,
# ``CHANGE-TO-A-UNIQUE-64-CHAR-SECRET-KEY``, ``YourSecurePassword123!``. In any case the word ends at a separator or at the
# end of the value; written in camel case it ends at the next capital. A word that runs on is part of a password:
# ``Yourdog2012!`` and ``ENTERPRISE2012!`` are secrets.
_PLACEHOLDER_START_RE = regex.compile(
    r"(?i:your|change|replace|example|placeholder|dummy|sample|insert|enter)(?:[-_]|$)"
    r"|(?:[Yy]our|[Cc]hange|[Rr]eplace|[Ee]xample|[Pp]laceholder|[Dd]ummy|[Ss]ample|[Ii]nsert|[Ee]nter)(?=[A-Z])"
)


def is_confirmed_match(rule_id: str, match: regex.Match[str]) -> bool:
    """Whether *match*, which the pattern of the rule *rule_id* found, is a real hit; a rule without a check always is."""
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
    if any(ellipsis in value for ellipsis in _ELLIPSES):
        return False
    end = _VALUE_END_RE.search(value)
    if end is not None:
        value = value[: end.start()]
    start = match.start("value")
    span = secret_value_span(match.string, start, start + len(value), allow_letters_only=False, key=groups.get("key") or "")
    return span is not None and not _PLACEHOLDER_START_RE.match(value)
